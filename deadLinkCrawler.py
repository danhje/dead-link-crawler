from http.client import BadStatusLine
from typing import Optional, List
import asyncio
import aiohttp
import ssl

from aiohttp.web_exceptions import HTTPException
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from time import time
import uvloop


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

SSL_CONTEXT = ssl.SSLContext()
PARSABLE_CONTENT_TYPES = ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml')


class Link:
    """The Link class represents links."""

    def __init__(self,
                 relative_target: str,
                 found_on: Optional[str] = None,
                 link_title: Optional[str] = None,
                 works: Optional[bool] = None,
                 target_body: Optional[str] = None) -> None:
        self.relative_target = relative_target
        self.found_on = found_on
        self.link_title = link_title
        self.works = works
        self.target_body = target_body

    def __str__(self) -> str:
        return self.absolute_target

    @property
    def absolute_target(self) -> str:
        """Return absolute URL for the link."""

        if self.found_on:
            return urljoin(self.found_on, self.relative_target)
        else:
            return self.relative_target


def print_results(links: List[Link]) -> None:
    """Print out a summary of the given list of links."""

    print(f'{len(links)} have been checked.')

    dead_links = [link for link in links if link.works is False]

    grouped_links = {}
    for link in dead_links:
        if link.found_on in grouped_links:
            grouped_links[link.found_on].append(link)
        else:
            grouped_links[link.found_on] = [link]
    if grouped_links:
        for foundOn, dead_links in grouped_links.items():
            print(f'On the page {foundOn}, the following links were dead:')
            for dead_link in dead_links:
                print(f'  Link title: {dead_link.link_title}')
                print(f'  Link URL: {dead_link.absolute_target}')
    else:
        print('No dead links have been found.')


def _link_in_list(lst: List[Link], link: Link) -> bool:
    return link.absolute_target in (checked_link.absolute_target for checked_link in lst)


def _link_is_internal(domain, link: Link) -> bool:
    return domain == '.'.join(urlparse(link.absolute_target).netloc.split('.')[-2:])


def _find_links(html: str) -> List[Link]:
    return [
        Link(relative_target=href, link_title=(aTag.text or '<untitled>'))
        for aTag in BeautifulSoup(html, features="html.parser").find_all('a')
        if (href := aTag.attrs.get('href')) is not None
    ]


def _should_queue_link(link: Link, queued_links: List[Link], checked_links: List[Link], domain: str) -> bool:
    return (
        not _link_in_list(checked_links, link) and
        not _link_in_list(queued_links, link) and
        _link_is_internal(domain, link)
    )


def _parse_completed_tasks(tasks, queued_links, checked_links, verbose, domain):
    completed_tasks = [task for task in tasks if task.done()]

    for task in completed_tasks:
        parent_link = task.result()
        if verbose and parent_link.works is False:
            print(f'Dead link with title "{parent_link.link_title}" and target '
                  f'{parent_link.absolute_target} found on {parent_link.found_on}')
        if parent_link.target_body:
            child_links_found = _find_links(parent_link.target_body)
            for child_link in child_links_found:
                child_link.found_on = parent_link.absolute_target
                if _should_queue_link(child_link, queued_links, checked_links, domain):
                    queued_links.append(child_link)


def _start_additional_tasks_from_queue(
        session: aiohttp.ClientSession,
        tasks: list,
        queued_links: List[Link],
        max_req: int,
        checked_links: List[Link],
        error_text: str,
) -> None:
    count = min(len(queued_links), max(0, max_req - len(tasks)))
    for _ in range(count):
        next_link = queued_links.pop(0)
        checked_links.append(next_link)
        new_task = asyncio.create_task(_fetch(session, next_link, error_text))
        tasks.append(new_task)


def _should_print_status(last_status_print_time: float, freq: float = 10.0) -> bool:
    return time() - last_status_print_time > freq


def _print_status(checked_links: list) -> float:
    n_dead = len([link for link in checked_links if link.works is False])
    print(f'Status: {len(checked_links)} links checked. {n_dead} dead.')
    return time()


async def _fetch(session: aiohttp.ClientSession, link: Link, error_text: str) -> Link:
    try:
        async with session.head(link.absolute_target, ssl=SSL_CONTEXT) as head_response:
            if head_response.status >= 401:
                link.works = False
                return link
            try:
                content_type = head_response.headers['content-type'].lower()
            except AttributeError:  # contentType is None
                parsable = True
            else:  # ContentType is not None
                parsable = any(t in content_type for t in PARSABLE_CONTENT_TYPES)

            if not parsable:
                link.works = True
                return link

            async with session.get(link.absolute_target, ssl=SSL_CONTEXT) as response:
                body = await response.text()
                if error_text in body:
                    link.works = False
                    return link
                link.target_body = body
                link.works = True
                return link
    except HTTPException:
        link.works = False
        return link


async def main(
    url: str,
    max_req: int = 10,
    error_text: str = 'Not Found',
    verbose: bool = True
) -> List[Link]:
    start_link = Link(relative_target=url, link_title="<Initial URL>")
    tasks = []
    queued_links = [start_link]
    checked_links = []
    last_print_status_time = 0.0
    domain = '.'.join(urlparse(start_link.absolute_target).netloc.split('.')[-2:])

    async with aiohttp.ClientSession() as session:
        while tasks or queued_links:
            _parse_completed_tasks(tasks, queued_links, checked_links, verbose, domain)
            tasks = [task for task in tasks if not task.done()]
            _start_additional_tasks_from_queue(session, tasks, queued_links, max_req, checked_links, error_text)
            if verbose and _should_print_status(last_print_status_time):
                last_print_status_time = _print_status(checked_links)
            await asyncio.sleep(0.01)
        return checked_links


def start_crawl(
    url: str,
    max_concurrent_requests: int = 10,
    error_text: str = 'Not Found',
    verbose: bool = True
) -> List[Link]:
    """Starts the crawl.

    Args:
        url: The URL to start the crawl from.
        max_concurrent_requests: The maximum number of concurrent requests.
        error_text: The text to look for in the response body to determine if the link is dead.
            The http status code is also checked.
        verbose: If True, immediately report broken links found during the crawl.

    Returns:
        A list of Link objects, with the 'works' attribute set to True or False.
    """

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(main(url, max_concurrent_requests, error_text, verbose))


if __name__ == '__main__':
    start = time()
    results = start_crawl('http://danielhjertholm.me/prosjekter.htm', verbose=True)
    print_results(results)
    end = time()
    print(f'Total time: {end - start} seconds')

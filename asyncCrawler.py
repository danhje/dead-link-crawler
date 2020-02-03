import asyncio
import aiohttp
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class Link:

    def __init__(self, relativeTarget, foundOn=None, linkTitle=None, works=None, targetBody=None):
        self.relativeTarget = relativeTarget
        self.foundOn = foundOn
        self.linkTitle = linkTitle
        self.works = works
        self.targetBody = targetBody

    @property
    def absoluteTarget(self):
        if self.foundOn:
            return urljoin(self.foundOn, self.relativeTarget)
        else:
            return self.relativeTarget


class LinkScanner(HTMLParser):

    def __init__(self):
        super(LinkScanner, self).__init__(convert_charrefs=True)
        self.urls = []
        self.currentlyInATag = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.currentlyInATag = True
            for attr in attrs:
                if attr[0] == 'href':
                    newLink = Link(relativeTarget=attr[1])
                    self.urls.append(newLink)

    def handle_data(self, data):
        if self.currentlyInATag:
            self.urls[-1].linkTitle = data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.currentlyInATag = False

    def popUrls(self):
        urls = self.urls
        self.urls = []
        return urls


async def fetch(session, link):
    assert(isinstance(link, Link))
    try:
        async with session.head(link.absoluteTarget, ssl=sslContext) as response:
            if response.status >= 401:
                link.works = False
                return link
            contentType = response.headers.get('content-type').lower()
            parsable = any(t in contentType for t in ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml'))
            if parsable:
                async with session.get(link.absoluteTarget, ssl=sslContext) as response:
                    body = await response.text()
                    if errorText in body:
                        link.works = False
                        return link
                    else:
                        link.targetBody = body
                        link.works = True
                        return link
            else:
                link.works = True
                return link
    except Exception:
        link.works = False
        return link


def linkAlreadyChecked(link):
    return link.absoluteTarget in (checkedLink.absoluteTarget for checkedLink in checkedLinks)


def linkAlreadyQueued(link):
    return link.absoluteTarget in (queuedLink.absoluteTarget for queuedLink in queuedLinks)


def onSameDomain(firstLink, secondLink):
    firstDomain = '.'.join(urlparse(firstLink.absoluteTarget).netloc.split('.')[-2:])
    secondDomain = '.'.join(urlparse(secondLink.absoluteTarget).netloc.split('.')[-2:])
    return firstDomain == secondDomain


async def main():
    linkSkanner = LinkScanner()
    startLink = Link(foundOn='http://danielhjertholm.me/prosjekter.htm', relativeTarget='http://danielhjertholm.me/prosjekter.htm')
    queuedLinks.append(startLink)
    async with aiohttp.ClientSession() as session:
        tasks = []
        simultaneousUrlFetches = 10
        while True:
            completedTasks = [task for task in tasks if task.done()]
            tasks = [task for task in tasks if not task.done()]

            for task in completedTasks:
                parentLink = task.result()
                if not parentLink.works:
                    print(f'Dead link with title "{parentLink.linkTitle}" and target {parentLink.absoluteTarget} found on {parentLink.foundOn}')
                if parentLink.targetBody:
                    linkSkanner.feed(parentLink.targetBody)
                    childLinksFound = linkSkanner.popUrls()
                    for childLink in childLinksFound:
                        childLink.foundOn = parentLink.absoluteTarget
                        if not linkAlreadyChecked(childLink) and not linkAlreadyQueued(childLink) and onSameDomain(parentLink, childLink):
                            queuedLinks.append(childLink)

            if len(tasks) < simultaneousUrlFetches and len(queuedLinks) > 0:
                for i in range(simultaneousUrlFetches - len(tasks)):
                    if len(queuedLinks) > 0:
                        nextLink = queuedLinks.pop(0)
                        checkedLinks.append(nextLink)
                        newtask = asyncio.create_task(fetch(session, nextLink))
                        tasks.append(newtask)

            if len(tasks) == 0 and len(queuedLinks) == 0:
                break
            await asyncio.sleep(0.01)


if __name__ == '__main__':
    sslContext = ssl.SSLContext()
    errorText = 'Not Found'
    checkedLinks = []
    queuedLinks = []

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    deadLinks = [link.absoluteTarget for link in checkedLinks if not link.works]
    print(f'{len(checkedLinks)} URLs checked. Of those, {len(deadLinks)} were dead.')
    if len(deadLinks) > 0:
        print('Dead urls:\n' + '\n'.join(deadLinks))

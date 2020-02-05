import asyncio
import aiohttp
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from time import time


class Link:
    """The Link class represents links.

    Example:

    >>> link = Link('https://domain.com')
    >>> isinstance(link, Link)
    True
    """

    def __init__(self, relativeTarget, foundOn=None, linkTitle=None, works=None, targetBody=None):
        self.relativeTarget = relativeTarget
        self.foundOn = foundOn
        self.linkTitle = linkTitle
        self.works = works
        self.targetBody = targetBody

    def __str__(self):
        return self.absoluteTarget

    @property
    def absoluteTarget(self):
        """Return absolute URL for the link.

        Example:

        >>> link = Link('about', foundOn='https://domain.com/home')
        >>> print(link.absoluteTarget)
        https://domain.com/about

        >>> link = Link('https://otherdomain.com', foundOn='https://domain.com/home')
        >>> print(link.absoluteTarget)
        https://otherdomain.com
        """

        if self.foundOn:
            return urljoin(self.foundOn, self.relativeTarget)
        else:
            return self.relativeTarget


class LinkScanner(HTMLParser):
    """Parser that looks for links in HTML.

    Example:

    >>> parser = LinkScanner()
    >>> parser.feed('<html><body><img src="smiley.gif"><a href="https://domain.com/somepage.htm">Link to some page</a></body></html>')
    >>> linksFound = parser.popLinks()
    >>> print(linksFound[0])
    https://domain.com/somepage.htm
    """

    def __init__(self):
        super(LinkScanner, self).__init__(convert_charrefs=True)
        self.links = []
        self.currentlyInATag = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr in attrs:
                if attr[0] == 'href':
                    self.currentlyInATag = True
                    newLink = Link(relativeTarget=attr[1])
                    self.links.append(newLink)

    def handle_data(self, data):
        if self.currentlyInATag:
            self.links[-1].linkTitle = data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.currentlyInATag = False

    def popLinks(self):
        """Return a list of links that were found during parsing.

        links are of type 'Link'.

        Example:

        >>> parser = LinkScanner()
        >>> parser.feed('<html><body><img src="smiley.gif"><a href="https://domain.com/somepage.htm">Link to some page</a></body></html>')
        >>> linksFound = parser.popLinks()
        >>> isinstance(linksFound[0], Link)
        True
        >>> print(linksFound[0])
        https://domain.com/somepage.htm
        """
        links = self.links
        self.links = []
        return links


class DeadLinkCrawler:
    """Looks for dead (broken) links on a domain.

    Example:

    >>> crawler = DeadLinkCrawler()
    >>> crawler.startCrawl('http://danielhjertholm.me', verbose=False)
    >>> crawler.printDeadLinks()
    No dead links have been found.
    >>> len(crawler.checkedLinks)
    2
    >>> len(list(crawler.deadLinks))
    0
    """

    def __init__(self):
        self.checkedLinks = []
        self._linkSkanner = LinkScanner()
        self._sslContext = ssl.SSLContext()
        self._queuedLinks = []
        self._domain = None
        self._parsableContentTypes = ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml')

    def startCrawl(self, url, maxSimultanousUrlFetches=10, errorText='Not Found', verbose=True):
        self._verbose = verbose
        self._maxSimultanousUrlFetches = maxSimultanousUrlFetches
        self._errorText = errorText
        self._domain = '.'.join(urlparse(url).netloc.split('.')[-2:])
        startLink = Link(relativeTarget=url, linkTitle='Initial URL')
        self._queuedLinks.append(startLink)
        self._loop = asyncio.get_event_loop()
        self._loop.run_until_complete(self._main())

    def printDeadLinks(self):
        sortedLinks = {}
        for link in self.deadLinks:
            if link.foundOn in sortedLinks:
                sortedLinks[link.foundOn].append(link)
            else:
                sortedLinks[link.foundOn] = [link]
        if len(sortedLinks) > 0:
            for foundOn, deadLinks in sortedLinks.items():
                print(f'On the page {foundOn}, the following links were dead:')
                for deadLink in deadLinks:
                    print(f'  Link title: {deadLink.linkTitle}')
                    print(f'  Link URL: {deadLink.absoluteTarget}')
        else:
            print('No dead links have been found.')

    @property
    def deadLinks(self):
        return (link for link in self.checkedLinks if link.works is False)

    def _linkAlreadyChecked(self, link):
        return link.absoluteTarget in (checkedLink.absoluteTarget for checkedLink in self.checkedLinks)

    def _linkAlreadyQueued(self, link):
        return link.absoluteTarget in (queuedLink.absoluteTarget for queuedLink in self._queuedLinks)

    def _linkIsInternal(self, link):
        linkDomain = '.'.join(urlparse(link.absoluteTarget).netloc.split('.')[-2:])
        return linkDomain == self._domain

    async def _fetch(self, session, link):
        assert(isinstance(link, Link))
        try:
            async with session.head(link.absoluteTarget, ssl=self._sslContext) as response:
                if response.status >= 401:
                    link.works = False
                    return link

                try:
                    contentType = response.headers.get('content-type').lower()
                except AttributeError:  # contentType is None
                    parsable = True
                else:  # ContentType is not None
                    parsable = any(t in contentType for t in self._parsableContentTypes)

                if parsable:
                    async with session.get(link.absoluteTarget, ssl=self._sslContext) as response:
                        body = await response.text()
                        if self._errorText in body:
                            link.works = False
                            return link
                        else:
                            link.targetBody = body
                            link.works = True
                            return link
                else:
                    link.works = True
                    return link
        except Exception as e:
            link.works = False
            return link

    async def _main(self):
        async with aiohttp.ClientSession() as session:
            tasks = []
            lastStatusPrintoutTime = time() - 7.0
            while True:
                completedTasks = [task for task in tasks if task.done()]
                tasks = [task for task in tasks if not task.done()]

                for task in completedTasks:
                    parentLink = task.result()
                    if self._verbose and parentLink.works is False:
                        print(f'Dead link with title "{parentLink.linkTitle}" and target {parentLink.absoluteTarget} found on {parentLink.foundOn}')
                    if parentLink.targetBody:
                        self._linkSkanner.feed(parentLink.targetBody)
                        childLinksFound = self._linkSkanner.popLinks()
                        self._linkSkanner.reset()
                        for childLink in childLinksFound:
                            childLink.foundOn = parentLink.absoluteTarget
                            if not self._linkAlreadyChecked(childLink) and not self._linkAlreadyQueued(childLink) and self._linkIsInternal(childLink):
                                self._queuedLinks.append(childLink)

                if len(tasks) < self._maxSimultanousUrlFetches and len(self._queuedLinks) > 0:
                    for i in range(self._maxSimultanousUrlFetches - len(tasks)):
                        if len(self._queuedLinks) > 0:
                            nextLink = self._queuedLinks.pop(0)
                            self.checkedLinks.append(nextLink)
                            newtask = asyncio.create_task(self._fetch(session, nextLink))
                            tasks.append(newtask)

                if time() - lastStatusPrintoutTime > 10:
                    lastStatusPrintoutTime = time()
                    print(f'Status: {len(self.checkedLinks)} links checked. {len([1 for link in crawler.checkedLinks if link.works is False])} dead.')
                    # Must use "is False" above, otherwise the default value None will evaluate as False for the ~ _maxSimultanousUrlFetches links that are currently being fetched.

                if len(tasks) == 0 and len(self._queuedLinks) == 0:
                    if self._verbose:
                        print(f'Crawl finished. Links checked: {len(crawler.checkedLinks)}. Dead links found: {len([1 for link in crawler.checkedLinks if link.works is False])}')
                    break
                await asyncio.sleep(0.01)


if __name__ == '__main__':
    import doctest
    doctest.testmod()

    crawler = DeadLinkCrawler()
    crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm', verbose=True)
    crawler.printDeadLinks()
    checkedLinks = crawler.checkedLinks
    deadLinks = list(crawler.deadLinks)

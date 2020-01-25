import asyncio
import aiohttp
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class LinkScanner(HTMLParser):

    def __init__(self):
        super(LinkScanner, self).__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if (tag == 'a'):
            for attr in attrs:
                if attr[0] == 'href':
                    relativeURL = attr[1]
                    self.urls.append(relativeURL)

    def popUrls(self):
        urls = self.urls
        self.urls = []
        return urls


async def fetch(session, url, foundOn):
    try:
        async with session.head(url, ssl=sslContext) as response:
            if response.status >= 401:
                return (url, foundOn, 'bad link')
            contentType = response.headers.get('content-type').lower()
            parsable = any(t in contentType for t in ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml'))
            if parsable:
                async with session.get(url, ssl=sslContext) as response:
                    body = await response.text()
                    if errorText in body:
                        return (url, foundOn, 'bad link')
                    return (url, foundOn, body)
            else:
                return (url, foundOn, 'not parsable')
    except Exception:
        return (url, foundOn, 'bad link')


async def main():
    linkSkanner = LinkScanner()
    queuedUrls = [('http://danielhjertholm.me/prosjekter.htm', 'http://danielhjertholm.me/prosjekter.htm')]
    async with aiohttp.ClientSession() as session:
        tasks = []
        simultaneousUrlFetches = 10
        urlCount = 0
        previousUrlCount = 0
        while True:
            completedTasks = [task for task in tasks if task.done()]
            tasks = [task for task in tasks if not task.done()]

            for task in completedTasks:
                url, foundOn, result = task.result()
                if result == 'bad link':
                    print(f'Bad: {url} on {foundOn}')
                    deadURLs.append(url)
                if result != 'not parsable':
                    linkSkanner.feed(result)  # data.decode(encoding=encoding)
                    relativeUrlsFound = linkSkanner.popUrls()
                    foundOnDomain = '.'.join(urlparse(url).netloc.split('.')[-2:])
                    for relativeURL in relativeUrlsFound:
                        absoluteURL = urljoin(url, relativeURL)
                        linkToDomain = '.'.join(urlparse(absoluteURL).netloc.split('.')[-2:])
                        if absoluteURL not in checkedURLs and absoluteURL not in queuedUrls and linkToDomain == foundOnDomain:
                            queuedUrls.append((absoluteURL, url))

            if len(tasks) < simultaneousUrlFetches and len(queuedUrls) > 0:
                for i in range(simultaneousUrlFetches - len(tasks)):
                    if len(queuedUrls) > 0:
                        nextUrl, foundOn = queuedUrls.pop(0)
                        checkedURLs.append(nextUrl)
                        newtask = asyncio.create_task(fetch(session, nextUrl, foundOn))
                        tasks.append(newtask)

            if len(tasks) == 0 and len(queuedUrls) == 0:
                break
            await asyncio.sleep(0.01)


if __name__ == '__main__':
    sslContext = ssl.SSLContext()
    errorText = 'Not Found'
    checkedURLs = []
    deadURLs = []

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    print(f'{len(checkedURLs)} URLs checked. Of those, {len(deadURLs)} were dead.')
    if len(deadURLs) > 0:
        print('Dead urls:\n' + '\n'.join(deadURLs))

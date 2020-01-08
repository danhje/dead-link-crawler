from html.parser import HTMLParser
from urllib.request import urlopen
from urllib.parse import urljoin, urlparse
from time import sleep
import ssl


class MyHTMLParser(HTMLParser):

    def __init__(self):
        super(MyHTMLParser, self).__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if (tag == 'a'):
            for attr in attrs:
                if attr[0] == 'href':
                    relativeURL = attr[1]
                    self.urls.append(relativeURL)

    def clearUrls(self):
        self.urls = []


class Crawler:

    def __init__(self):
        self.checkedURLs = []
        self.deadURLs = []
        self.parser = MyHTMLParser()
        self._warningColor = '\033[91m'
        self._endColor = '\033[0m'

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type:
            print(f'exc_type: {exc_type}')
            print(f'exc_value: {exc_value}')
            print(f'exc_traceback: {exc_traceback}')

    def _isInternal(self, domain, url):
        return domain in url

    def _appendCheckedUrl(self, url):
        if url not in self.checkedURLs:
            self.checkedURLs.append(url)

    def _appendDeadUrl(self, url):
        if url not in self.deadURLs:
            self.deadURLs.append(url)

    def startCrawl(self, url):
        self.checkedURLs.append(url)
        try:
            with urlopen(url) as response:
                encoding = response.info().get_charset()
                data = response.read()
                # headerEncoding = response.headers.get_content_charset()
        except ssl.SSLError:
            print(f'{self._warningColor}Found a dead link: {url}{self._endColor}')
            self._appendDeadUrl(url)
            return
        except OSError:
            print(f'{self._warningColor}Found a dead link: {url}{self._endColor}')
            self._appendDeadUrl(url)
            return
        except ValueError:
            print(f'{self._warningColor}Found a dead link: {url}{self._endColor}')
            self._appendDeadUrl(url)
            return

        encoding = 'utf-8' if encoding is None else encoding  # set default
        try:
            self.parser.feed(data.decode("utf-8"))
        except UnicodeDecodeError as e:
            self.parser.feed(str(data))

        domain = urlparse(url).netloc
        relativeUrlsFound = self.parser.urls
        self.parser.clearUrls()
        for relativeURL in relativeUrlsFound:
            absoluteURL = urljoin(url, relativeURL)
            if absoluteURL not in self.checkedURLs and self._isInternal(domain, absoluteURL):
                # print(f'Checking url {absoluteURL}')
                self.startCrawl(absoluteURL)


if __name__ == "__main__":

    # crawler = Crawler()
    # crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm')
    # print(f'Checked {len(crawler.checkedURLs)}, of which {len(crawler.deadURLs)} were dead.')
    # deadUrls = '\n'.join(crawler.deadURLs)
    # print(f'List of dead urls:\n{deadUrls}')

    with Crawler() as crawler:
        crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm')
        print(f'{len(crawler.checkedURLs)} urls checked, of which {len(crawler.deadURLs)} were dead.')
        deadUrls = '\n'.join(crawler.deadURLs)
        print(f'List of dead urls:\n{deadUrls}')

# TODO:
# make isInternal smarter. Will anser yes for https://wrongdomiain.com/rightcomain.com
# paralell requests
# http status codes
# don't download binary files
# delay

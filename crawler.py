from html.parser import HTMLParser
from urllib.request import FancyURLopener
from urllib.parse import urljoin
from time import sleep
import ssl


parsedURLs = []
deadURLs = []


def shouldParseUrl(url):
    if url in parsedURLs:
        return False
    if 'danielhjertholm.me' not in url:
        return False
    if 'mailto' in url:
        return False
    return True

# Create a subclass and override the handler methods
class myParser(HTMLParser):

    def __init__(self, url, level):
        super(myParser, self).__init__()
        sleep(0.1)
        print('Checking URL', url)
        self.__level = level
        self.__done = False
        self.__currentlyParsingDeadATag = False
        self.__currentlyParsingTitleTag = False
        self.__url = url
        self.linkWasDead = False
        parsedURLs.append(self.__url)
        try:
            opener = FancyURLopener({})
            f = opener.open(self.__url)
            data = f.read()
        except ssl.SSLError:
            return
        except OSError:
            return
        except ValueError:
            if not self.__url in deadURLs:
                print()
                print('Found a dead link:', self.__url)
                deadURLs.append(self.__url)
                self.linkWasDead = True
            self.__done = True
            return

        try:
            text = data.decode(errors='replace')
        except UnicodeDecodeError:
            pass
            #print('This is a binary file:', self.__url)
        else:
            try:
                self.feed(text)
            except ValueError:
                pass
            except ssl.SSLError:
                pass

    def handle_starttag(self, tag, attrs):
        if self.__done:
            return

        self.__currentlyParsingTitleTag = (tag == 'title')

        if self.__currentlyParsingTitleTag:
            return

        if (tag == 'a'):
            url = attrs
            for t in url:
                if t[0] == 'href':
                    url = t[1]
                    url = urljoin(self.__url, url)

            if shouldParseUrl(url):
                parser = myParser(url, level=self.__level+1)
                if parser.linkWasDead:
                    self.__currentlyParsingDeadATag = True

    def handle_data(self, data):
        if self.__done:
            return

        if self.__currentlyParsingTitleTag:
            if 'Not Found' in data:
                if not self.__url in deadURLs:
                    print()
                    print('Found a dead link:', self.__url)
                    deadURLs.append(self.__url)
                    self.linkWasDead = True
                self.__done = True
                return

            self.__currentlyParsingATag = False
            self.__currentlyParsingTitleTag = False
            return

        if self.__currentlyParsingDeadATag:
            print('The link was found on the following page:', self.__url)
            if data.strip() == '':
                data = '<Link without text. Perhaps image?>'
            print('The link had the following title:', data)
            self.__currentlyParsingDeadATag = False
            self.__currentlyParsingTitleTag = False





startUrl = 'http://danielhjertholm.me/prosjekter.htm'
if shouldParseUrl(startUrl):
    parser = myParser(startUrl, level=1)

print()
print()
print(len(parsedURLs), 'links have been checked. Af those,', len(deadURLs), 'were dead.')
print('Dead links:')
print(deadURLs)
print()
print('Linker that were checked:')
print(parsedURLs)
print()

# Dead Link Crawler
An efficient, asynchronous crawler that identifies broken links on a given domain.

## Installation
```
git clone https://github.com/danhje/dead-link-crawler.git
cd dead-link-crawler
pipenv install
```

## Usage
To start Python from within the virtual environment:
```
pipenv run python
```
To start the crawl and print the results:
```
from deadLinkCrawler import DeadLinkCrawler

crawler = DeadLinkCrawler()
crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm', verbose=True)
crawler.printDeadLinks()
checkedLinks = crawler.checkedLinks
deadLinks = list(crawler.deadLinks)
```


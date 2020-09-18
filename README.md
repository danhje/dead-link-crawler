# Dead Link Crawler
An efficient, asynchronous crawler that identifies broken links on a given domain.

## Installation
```shell
git clone https://github.com/danhje/dead-link-crawler.git
cd dead-link-crawler
pipenv install
```

## Usage
To start Python from within the virtual environment:
```shell
pipenv run python
```
To start the crawl and print the results:
```python
from deadLinkCrawler import DeadLinkCrawler

crawler = DeadLinkCrawler()
crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm', verbose=True)
crawler.printDeadLinks()
checkedLinks = crawler.checkedLinks
deadLinks = list(crawler.deadLinks)
```


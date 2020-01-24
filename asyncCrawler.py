import asyncio
import aiohttp
import ssl


sslContext = ssl.SSLContext()


async def fetch(session, url):
    print(f'fetching url {url}')
    async with session.head(url, ssl=sslContext) as response:
        parsable = response.headers.get('content-type').lower() in ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml')
        if parsable:
            async with session.get(url, ssl=sslContext) as response:
                body = await response.text()
                return body
        else:
            return 'not parsable'


async def main():
    queuedUrls = ['http://danielhjertholm.me/prosjekter.htm', 'http://danielhjertholm.me/om.htm']
    async with aiohttp.ClientSession() as session:
        tasks = []
        while True:
            for i in range(len(tasks)):
                task = tasks[i]
                if task.done():
                    # print(task.result())
                    del(tasks[i])
            if len(tasks) < 3 and len(queuedUrls) > 0:
                url = queuedUrls.pop(0)
                newtask = asyncio.create_task(fetch(session, url))
                tasks.append(newtask)
            print(f'Number of tasks: {len(asyncio.all_tasks())}')
            if len(tasks) == 0 and len(queuedUrls) == 0:
                print('Nothing more to do')
                break
            await asyncio.sleep(0.1)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

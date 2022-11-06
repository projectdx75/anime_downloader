import asyncio
import threading
import traceback
from asyncio import Task
from typing import Awaitable, T

from loguru import logger


def start_cor(loop, url):
    fut = asyncio.run_coroutine_threadsafe(hello_async(url), loop)
    print(fut.result())


def _start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


_LOOP = asyncio.new_event_loop()
_LOOP_THREAD = threading.Thread(
    target=_start_background_loop, args=(_LOOP,), daemon=True
)
_LOOP_THREAD.start()


# =================================================================#
def asyncio_run(future, as_task=True):
    """
    A better implementation of `asyncio.run`.

    :param future: A future or task or call of an async method.
    :param as_task: Forces the future to be scheduled as task (needed for e.g. aiohttp).
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # no event loop running:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(_to_task(future, as_task, loop))
    else:
        import nest_asyncio
        nest_asyncio.apply(loop)
        return asyncio.run(_to_task(future, as_task, loop))


def asyncio_run2(coro: Awaitable[T], timeout=60) -> T:
    """
    Runs the coroutine in an event loop running on a background thread,
    and blocks the current thread until it returns a result.
    This plays well with gevent, since it can yield on the Future result call.

    :param coro: A coroutine, typically an async method
    :param timeout: How many seconds we should wait for a result before raising an error
    """
    try:
        return asyncio.run_coroutine_threadsafe(coro, _LOOP).result(timeout=timeout)
    except Exception as e:
        logger.error("Exception:%s", e)
        logger.error(traceback.format_exc())


def _to_task(future, as_task, loop):
    if not as_task or isinstance(future, Task):
        return future
    return loop.create_task(future)


def hello_sync(url: str):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # browser = p.chromium.launch()
        browser = p.chromium.connect_over_cdp('http://192.168.0.2:14444')
        page = browser.new_page()
        page.goto(url)
        print(page.title())
        browser.close()


async def _test(url):
    await asyncio.sleep(2)
    print('_test')
    return 'ok'


async def compute(x, y):
    print("Compute %s + %s ..." % (x, y))
    await asyncio.sleep(1.0)
    return x + y


async def print_sum(x, y):
    result = await compute(x, y)
    print("%s + %s = %s" % (x, y, result))


async def _thread(url, loop):
    if loop is not None:
        # future = asyncio.run_coroutine_threadsafe(hello_async(url), loop)
        # future = asyncio.run_coroutine_threadsafe(_test(url), loop)

        # print(f"Future  --")
        # print(" 2 ")
        # print(" Result ", future.result())
        # print(" 3 ")
        # loop.run_until_complete(print_sum(1, 2))
        loop.run_until_complete(hello_async(url, loop))
        print("")


async def hello_async(url: str, loop=None):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        print("here")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        print(page.title())

        await browser.close()


async def hello(url: str):
    from playwright.async_api import async_playwright
    # from playwright_stealth import stealth_sync, stealth_async
    print("hi")
    try:
        from gevent.event import AsyncResult
        print(AsyncResult())
        await asyncio.sleep(2)
        print("hi")
        # pw = await async_playwright().start()
        # print(pw)
        # browser = await pw.chromium.launch(headless=True)
        # print("Browser Launched-----------------")
        # page = await browser.new_page()
        # print("Browser new Page created ")
        # await page.goto(url)
        # LogicAniLife.response_data = await page.content()
        # return await page.content()
    except Exception as e:
        logger.error("Exception:%s", e)
        logger.error(traceback.format_exc())

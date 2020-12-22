import os
import re
import scrapelib
import lxml.html
from utils import dump_obj


def elem_to_str(item, inside=False):
    attribs = "  ".join(f"{k}='{v}'" for k, v in item.attrib.items())
    return f"<{item.tag} {attribs}> @ line {item.sourceline}"


class Selector:
    def __init__(self, *, min_items=1, max_items=None, num_items=None):
        self.min_items = min_items
        self.max_items = max_items
        self.num_items = num_items

    def match(self, element, *, min_items=None, max_items=None, num_items=None):
        items = list(self.get_items(element))
        num_items = self.num_items if num_items is None else num_items
        max_items = self.max_items if max_items is None else max_items
        min_items = self.min_items if min_items is None else min_items

        if num_items is not None and len(items) != num_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected {num_items}"
            )
        if min_items is not None and len(items) < min_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at least {min_items}"
            )
        if max_items is not None and len(items) > max_items:
            raise SelectorError(
                f"{self.get_display()} on {elem_to_str(element)} got {len(items)}, "
                f"expected at most {max_items}"
            )

        return items

    def match_one(self, element):
        return self.match(element, num_items=1)[0]


class XPath(Selector):
    def __init__(self, xpath, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.xpath = xpath

    def get_items(self, element):
        yield from element.xpath(self.xpath)

    def get_display(self):
        return f"XPath({self.xpath})"


class SimilarLink(Selector):
    def __init__(self, pattern, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.pattern = re.compile(pattern)

    def get_items(self, element):
        seen = set()
        for element in element.xpath("//a"):
            href = element.get("href")
            if href and href not in seen and self.pattern.match(element.get("href", "")):
                yield element
                seen.add(href)

    def get_display(self):
        return f"SimilarLink({self.pattern})"


class CSS(Selector):
    def __init__(self, css_selector, *, min_items=1, max_items=None, num_items=None):
        super().__init__(min_items=min_items, max_items=max_items, num_items=num_items)
        self.css_selector = css_selector

    def get_items(self, element):
        yield from element.cssselect(self.css_selector)

    def get_display(self):
        return f"CSS({self.css_selector})"


class NoSuchScraper(Exception):
    pass


class SelectorError(ValueError):
    pass


class Scraper(scrapelib.Scraper):
    def fetch_page_data(self, page):
        print(f"fetching {page.url} for {page.__class__.__name__}")
        data = self.get(page.url)
        page.set_raw_data(data)


class Page:
    def __init__(self, url):
        """
        a Page can be instantiated with a url & options (TBD) needed to fetch it
        """
        self.url = url

    def set_raw_data(self, raw_data):
        """ callback to handle raw data returned by grabbing the URL """
        self.raw_data = raw_data

    def get_data(self):
        """ return data extracted from this page and this page alone """
        raise NotImplementedError()


class HtmlPage(Page):
    def set_raw_data(self, raw_data):
        super().set_raw_data(raw_data)
        self.root = lxml.html.fromstring(raw_data.content)
        self.root.make_links_absolute(self.url)


class HtmlListPage(HtmlPage):
    """
    Simplification for HTML pages that get a list of items and process them.

    When overriding the class, instead of providing get_data, one must only provide
    a selector and a process_item function.
    """

    selector = None

    # common for a list page to only work on one URL, in which case it is more clear
    # to set it as a property
    def __init__(self, url=None):
        """
        a Page can be instantiated with a url & options (TBD) needed to fetch it
        """
        if url is not None:
            self.url = url

    def get_data(self):
        if not self.selector:
            raise NotImplementedError("must either provide selector or override scrape")
        items = self.selector.match(self.root)
        for item in items:
            item = self.process_item(item)
            yield item

    def process_item(self, item):
        return item


class Workflow:
    def __init__(self, initial_page, page_processor_cls, scraper=None):
        self.initial_page = initial_page
        self.page_processor_cls = page_processor_cls
        if not scraper:
            self.scraper = Scraper()

    def execute(self):
        directory = "_data"
        os.makedirs(directory, exist_ok=True)
        self.scraper.fetch_page_data(self.initial_page)

        for i, item in enumerate(self.initial_page.get_data()):
            # print(f"{i}:", _display(item))
            page = self.page_processor_cls(item["url"])
            self.scraper.fetch_page_data(page)
            data = page.get_data()
            dump_obj(data.to_dict(), output_dir=directory)

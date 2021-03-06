import re
import attr
import logging
from spatula import HtmlListPage, HtmlPage, XPath
from .common.people import Person, PeopleWorkflow

log = logging.getLogger("fl")


def fix_name(name):
    # handles cases like Watson, Jr., Clovis
    if ", " not in name:
        return name
    last, first = name.rsplit(", ", 1)
    return first + " " + last


@attr.s(auto_attribs=True)
class PartialPerson:
    name: str
    party: str
    district: str
    url: str
    image: str = ""  # default empty, required for Rep


class SenList(HtmlListPage):
    source = "http://www.flsenate.gov/Senators/"
    selector = XPath("//a[@class='senatorLink']")

    def process_item(self, item):
        name = " ".join(item.xpath(".//text()"))
        name = re.sub(r"\s+", " ", name).replace(" ,", ",").strip()

        if "Vacant" in name:
            self.skip()

        district = item.xpath("string(../../td[1])")
        party = item.xpath("string(../../td[2])")
        leg_url = item.get("href")

        return SenDetail(PartialPerson(name=name, party=party, district=district, url=leg_url))


class SenDetail(HtmlPage):
    contact_xpath = XPath('//h4[contains(text(), "Office")]')
    input_type = PartialPerson

    def process_page(self):
        email = self.root.xpath('//a[contains(@href, "mailto:")]')[0].get("href").split(":")[-1]

        p = Person(
            state="fl",
            chamber="upper",
            name=fix_name(self.input.name),
            party=str(self.input.party),
            district=str(self.input.district),
            email=email,
            image=str(self.root.xpath('//div[@id="sidebar"]//img/@src').pop()),
        )

        for item in self.contact_xpath.match(self.root):
            self.handle_office(item, p)

        return p

    def handle_office(self, office, person):
        (name,) = office.xpath("text()")
        if name == "Tallahassee Office":
            obj_office = person.capitol_office
        else:
            obj_office = person.district_office

        address_lines = [
            x.strip()
            for x in office.xpath("following-sibling::div[1]")[0].text_content().splitlines()
            if x.strip()
        ]

        clean_address_lines = []
        fax = phone = None
        PHONE_RE = r"\(\d{3}\)\s\d{3}\-\d{4}"
        after_phone = False

        for line in address_lines:
            if re.search(r"(?i)open\s+\w+day", address_lines[0]):
                continue
            elif "FAX" in line:
                fax = line.replace("FAX ", "")
                after_phone = True
            elif re.search(PHONE_RE, line):
                phone = line
                after_phone = True
            elif not after_phone:
                clean_address_lines.append(line)

        address = "; ".join(clean_address_lines)
        address = re.sub(r"\s{2,}", " ", address)
        obj_office.address = address
        obj_office.phone = phone
        obj_office.fax = fax


class RepContact(HtmlPage):
    input_type = PartialPerson

    def get_source_from_input(self):
        """
        Transform from
            /Sections/Representatives/details.aspx?MemberId=#&LegislativeTermId=#
        to:
            /Sections/Representatives/contactmember.aspx?MemberId=#&SessionId=#
        """
        return self.input.url.replace("details.aspx", "contactmember.aspx")

    def process_page(self):
        p = Person(
            state="fl",
            chamber="lower",
            name=fix_name(self.input.name),
            party=str(self.input.party),
            district=str(self.input.district),
            image=self.input.image,
        )
        for otype in ("district", "capitol"):
            odoc = self.root.xpath(f"//h3[@id='{otype}-office']/following-sibling::ul")
            if odoc:
                odoc = odoc[0]
            else:
                continue
            spans = odoc.xpath(".//span")

            office = p.capitol_office if otype == "capitol" else p.district_office
            office.address = "; ".join(
                line.strip()
                for line in spans[0].text_content().strip().splitlines()
                if line.strip()
            )
            office.voice = spans[1].text_content().strip()

        return p


class RepList(HtmlListPage):
    source = "https://www.myfloridahouse.gov/Representatives"
    # kind of wonky xpath to not get the partial term people at the bottom of the page
    selector = XPath("(//div[@class='team-page'])[1]//div[@class='team-box']")

    IMAGE_BASE = "https://www.myfloridahouse.gov/"

    def process_item(self, item):
        name = item.xpath("./a/div[@class='team-txt']/h5/text()")[0].strip()
        party = item.xpath("./a/div[@class='team-txt']/p[1]/text()")[0].split()[0]
        district = item.xpath("./a/div[@class='team-txt']/p[1]/span/text()")[0].split()[-1]
        image = self.IMAGE_BASE + item.xpath(".//img")[0].attrib["data-src"]
        link = str(item.xpath("./a/@href")[0])

        return RepContact(
            PartialPerson(
                name=name,
                party=str(party),
                district=str(district),
                image=image,
                url=link,
            )
        )


senators = PeopleWorkflow(SenList)
reps = PeopleWorkflow(RepList)

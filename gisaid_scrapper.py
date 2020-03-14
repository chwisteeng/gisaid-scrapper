from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as cond
from selenium.common.exceptions import NoAlertPresentException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.firefox.options import Options
import time
from selenium.webdriver.common.action_chains import ActionChains
import tqdm
import glob
import os
import sys
import argparse, sys

METADATA_COLUMNS = [
    "Accession",
    "Collection date",
    "Location",
    "Host",
    "Additional location information",
    "Gender",
    "Patient age",
    "Patient status",
    "Specimen source",
    "Additional host information",
    "Outbreak",
    "Last vaccinated",
    "Treatment",
    "Sequencing technology",
    "Assembly method",
    "Coverage",
    "Comment",
    "Length"
]


class GisaidCoVScrapper:
    def __init__(
        self,
        headless: bool = False,
        whole_genome_only: bool = True,
        destination: str = "fastas",
    ):
        self.whole_genome_only = whole_genome_only

        self.destination = destination
        self.finished = False
        self.already_downloaded = 0
        self.samples_count = None
        self.new_downloaded = 0

        options = Options()
        options.headless = headless
        self.driver = webdriver.Firefox(options=options)
        self.driver.implicitly_wait(1000)

        if not os.path.exists(destination):
            os.makedirs(destination)

        self._update_cache()
        if os.path.isfile(destination + "/metadata.tsv"):
            self.metadata_handle = open(destination + "/metadata.tsv", "a")
        else:
            self.metadata_handle = open(destination + "/metadata.tsv", "w")
            self.metadata_handle.write("\t".join(METADATA_COLUMNS) + "\n")

    def login(self, username: str, password: str):
        self.driver.get("https://platform.gisaid.org/epi3/frontend")
        time.sleep(2)
        login = self.driver.find_element_by_name("login")
        login.send_keys(username)

        passwd = self.driver.find_element_by_name("password")
        passwd.send_keys(password)
        login_box = self.driver.find_element_by_class_name("form_button_submit")

        self.driver.execute_script("document.getElementById('sys_curtain').remove()")
        self.driver.execute_script(
            "document.getElementsByClassName('form_button_submit')[0].click()"
        )
        WebDriverWait(self.driver, 30).until(cond.staleness_of(login_box))

    def load_epicov(self):
        time.sleep(2)
        self._go_to_seq_browser()

        if self.whole_genome_only:
            print("Clicking")
            parent_form = self.driver.find_element_by_class_name("sys-form-fi-cb")
            inp = parent_form.find_element_by_tag_name("input")
            inp.click()
            time.sleep(2)

        self._update_metainfo()

    def _go_to_seq_browser(self):
        self.driver.execute_script("document.getElementById('sys_curtain').remove()")
        self.driver.find_element_by_link_text("EpiCoV™").click()

        time.sleep(3)

        self.driver.execute_script("document.getElementById('sys_curtain').remove()")
        self.driver.find_elements_by_xpath("//*[contains(text(), 'Browse')]")[0].click()

    def _update_metainfo(self):
        self.samples_count = int(
            self.driver.find_elements_by_xpath("//*[contains(text(), 'Total:')]")[
                0
            ].text.split(" ")[1]
        )
        self._update_cache()

    def _update_cache(self):
        res = [
            i.split("\\")[-1].split(".")[0]
            for i in glob.glob(f"{self.destination}/*.fasta")
        ]
        self.already_downloaded = res

        if self.samples_count is not None:
            samples_left = self.samples_count - len(res)
            if samples_left > 0:
                print(samples_left, "samples left")
                self.finished = False
            else:
                self.finished = True
                print("Finished!")

    def download_from_curr_page(self):
        time.sleep(1)

        parent_form = self.driver.find_element_by_class_name("yui-dt-data")
        rows = parent_form.find_elements_by_tag_name("tr")
        # time.sleep(2)

        for i in tqdm.trange(len(rows)):
            self._download_row(parent_form, i)

    def _download_row(self, parent_form, row_id):
        row = parent_form.find_elements_by_tag_name("tr")[row_id]
        col = row.find_elements_by_tag_name("td")[1]
        name = row.find_elements_by_tag_name("td")[2].text
        if name in self.already_downloaded:
            return

        self._action_click(col)

        iframe = self.driver.find_elements_by_tag_name("iframe")[0]

        self._save_data(iframe, name)

        self._action_click(self.driver.find_elements_by_tag_name("button")[1])
        self.driver.switch_to.default_content()
        time.sleep(1)

        self.new_downloaded += 1

    def _save_data(self, iframe, name):
        self.driver.switch_to.frame(iframe)
        pre = self.driver.find_elements_by_tag_name("pre")[0]
        fasta = pre.text

        # Handle metadata
        metadata = self.driver.find_elements_by_xpath(
            "//b[contains(text(), 'Sample information')]/../../following-sibling::tr"
        )[:16]

        res = f"{name}\t"
        for line in metadata:
            try:
                info = line.text.split(":")[1].strip().replace("\n", "")
                res += info
                res += "\t"
            except IndexError:
                res += "\t"
        res += str(len(fasta))
        self.metadata_handle.write(res + "\n")

        # Save FASTA
        with open(f"{self.destination}/{name}.fasta", "w") as f:
            for line in fasta.upper().split("\n"):
                f.write(line.strip())
                f.write("\n")

    def _action_click(self, element):
        action = ActionChains(self.driver)
        action.move_to_element(element).perform()
        time.sleep(1)
        element.click()
        time.sleep(1)

    def go_to_next_page(self):
        self.driver.find_element_by_xpath("//*[contains(text(), 'next >')]").click()
        self._update_metainfo()

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument('--username', '-u', help="Username for GISAID", type=str)
    parser.add_argument('--password', '-p', help="Password for GISAID", type=str)
    parser.add_argument('--filename', '-f', help="Path to file with credentials (alternative, default: credentials.txt)", type=str, default="credentials.txt")
    parser.add_argument('--destination', '-d', help="Destination directory (default: fastas/)", type=str, default="fastas/")
    parser.add_argument('--headless', '-q', help="Headless mode of scraping (experimental)", type=str2bool, nargs='?', default=False)
    parser.add_argument('--whole', '-w', help="Scrap whole genomes only", type=str2bool, nargs='?', default=False)

    args = parser.parse_args()
    args.headless = True if args.headless is None else args.headless
    args.whole = True if args.whole is None else args.whole  
    return args

if __name__ == "__main__":
    args = parse_args()

    if args.username is None or args.password is None:
        if args.filename is None:
            print(parser.format_help())
            sys.exit(-1)
        try:
            with open(args.filename) as f:
                login = f.readline()
                passwd = f.readline()
        except FileNotFoundError:
            print("File not found.")
            print(parser.format_help())
            sys.exit(-1)
    else:
        login = args.username
        passwd = args.password

    scrapper = GisaidCoVScrapper(args.headless, args.whole, args.destination)
    scrapper.login(login, passwd)
    scrapper.load_epicov()

    while not scrapper.finished:
        scrapper.download_from_curr_page()
        scrapper.go_to_next_page()
    print("New samples:", scrapper.new_downloaded)

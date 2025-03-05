import snoop
import time
import json
import enum
from dataclasses import dataclass
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests

LIBRARY_PREFIX = "https://webvpn.tsinghua.edu.cn/https/77726476706e69737468656265737421e3f24088693c6152301c9aa596522b204c02212b859d0a19"
LIBRARY_LIST_URL = LIBRARY_PREFIX + "/api.php/areas/1/tree/1"
LIBRARY_AREAS_URL = LIBRARY_PREFIX + "/api.php/areas/"
LIBRARY_SEATS_URL = LIBRARY_PREFIX + "/api.php/spaces_old/"
LIBRARY_DAYS_URL = LIBRARY_PREFIX + "/api.php/areadays/"


@dataclass
class Library:
    id: int
    name: str
    nameMerge: str
    enname: str
    ennameMerge: str


@dataclass
class LibraryFloor:
    id: int
    name: str
    enname: str
    parent: int


@dataclass
class LibrarySection:
    id: int
    name: str
    enname: str
    total: int
    available: int
    parent: int


Day = enum.Enum("Day", "Today Tomorrow")


@dataclass
class LibraryDay:
    id: int
    date: str
    startTime: str
    endTime: str
    day: Day


@dataclass
class LibrarySeat:
    id: int
    name: str
    type: int
    status: int
    parent: int


status_dict = {
    1: "空闲",
    4: "维护",
    6: "使用中",
    7: "临时离开",
}


class LibQuery:
    def __init__(self, session: requests.Session, headers: dict[str, str]):
        self.session = session
        self.headers = headers

    def get_json(self, url: str, params: dict | None = None) -> dict:
        response = self.session.get(
            url, headers=self.headers, allow_redirects=True, params=params
        )
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["status"] == 1
        return response_json

    def get_library_list(self) -> list[Library]:
        response_json = self.get_json(LIBRARY_LIST_URL)
        data_list = response_json["data"]["list"]
        return [
            Library(
                id=data["id"],
                name=data["name"],
                nameMerge=data["nameMerge"],
                enname=data["enname"],
                ennameMerge=data["ennameMerge"],
            )
            for data in data_list
            if data["isValid"] == 1
        ]

    def get_library_floors(self, library: Library) -> list[LibraryFloor]:
        response_json = self.get_json(LIBRARY_AREAS_URL + str(library.id))
        assert response_json["status"] == 1
        data_list = response_json["data"]["list"]["childArea"]
        return [
            LibraryFloor(
                id=data["id"],
                name=data["name"],
                enname=data["enname"],
                parent=library.id,
            )
            for data in data_list
            if data["isValid"] == 1
        ]

    def get_library_sections(
        self, floor: LibraryFloor, day: Day = Day.Today
    ) -> list[LibrarySection]:
        date = time.strftime(
            "%Y-%m-%d",
            time.localtime(time.time() + (86400 if day == day.Tomorrow else 0)),
        )
        response_json = self.get_json(
            LIBRARY_AREAS_URL + str(floor.id) + "/date/" + date
        )
        data_list = response_json["data"]["list"]["childArea"]
        return sorted(
            [
                LibrarySection(
                    id=data["id"],
                    name=data["name"],
                    enname=data["enname"],
                    total=data["TotalCount"],
                    available=data["TotalCount"] - data["UnavailableSpace"],
                    parent=floor.id,
                )
                for data in data_list
                if data["isValid"] == 1
            ],
            key=lambda x: x.id,
        )

    def get_library_day(
        self, section: LibrarySection, day: Day = Day.Today
    ) -> LibraryDay:
        date = time.strftime(
            "%Y-%m-%d",
            time.localtime(time.time() + (86400 if day == day.Tomorrow else 0)),
        )
        response_json = self.get_json(LIBRARY_DAYS_URL + str(section.id))
        data_list = response_json["data"]["list"]
        the_day = [
            LibraryDay(
                id=data["id"],
                date=data["day"],
                startTime=data["startTime"]["date"][11:16],
                endTime=data["endTime"]["date"][11:16],
                day=day,
            )
            for data in data_list
            if data["day"] == date
        ]
        assert len(the_day) == 1
        return the_day[0]

    def get_library_seats(
        self, section: LibrarySection, day: LibraryDay
    ) -> list[LibrarySeat]:
        now = time.strftime("%H:%M", time.localtime())
        response_json = self.get_json(
            LIBRARY_SEATS_URL,
            {
                "area": section.id,
                "segment": day.id,
                "day": day.date,
                "startTime": now if day.day == Day.Today else day.startTime,
                "endTime": day.endTime,
            },
        )
        data_list = response_json["data"]["list"]
        return [
            LibrarySeat(
                id=data["id"],
                name=data["name"],
                type=data["area_type"],
                status=data["status"],
                parent=section.id,
            )
            for data in data_list
        ]


def webvpn_login(username: str, password: str) -> LibQuery:
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    try:
        driver.get("https://webvpn.tsinghua.edu.cn/login?oauth_login=true")
        print("Browser opened. Logging in automatically...")
        driver.find_element(By.ID, "i_user").send_keys(username)
        driver.find_element(By.ID, "i_pass").send_keys(password)
        driver.execute_script("doLogin()")
        while "webvpn.tsinghua.edu.cn" not in driver.current_url:
            time.sleep(1)
        print("Login successful.")
        time.sleep(1)

        cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent")

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie["path"],
            )
        headers = {"User-Agent": user_agent}
    except Exception as e:
        print("An error occurred during login. Try logging in manually.")
        raise e
    finally:
        driver.quit()
        print("\nBrowser closed.")

    return LibQuery(session, headers)


def webvpn_login_manual():
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    try:
        driver.get("https://webvpn.tsinghua.edu.cn/login?oauth_login=true")
        print("Browser opened. Please log in through the browser interface.")
        input("Press Enter after you have successfully logged in...")

        cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent")

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie["path"],
            )
        headers = {"User-Agent": user_agent}
    finally:
        driver.quit()
        print("\nBrowser closed.")

    return LibQuery(session, headers)


def main():
    secrets = json.loads(open("secrets.json").read())
    lib = webvpn_login(secrets["username"], secrets["password"])
    lib_list = lib.get_library_list()
    snoop.pp(lib_list)
    lib_floors = lib.get_library_floors(lib_list[0])
    snoop.pp(lib_floors)
    lib_sections = lib.get_library_sections(lib_floors[0])
    snoop.pp(lib_sections)
    lib_day = lib.get_library_day(lib_sections[0])
    snoop.pp(lib_day)
    lib_seats = lib.get_library_seats(lib_sections[0], lib_day)
    snoop.pp(lib_seats)


if __name__ == "__main__":
    main()

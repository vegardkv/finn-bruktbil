

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


@dataclass
class CarListing:
    omregistrering: int  # NOK
    pris_eks_omreg: int  # NOK
    årsavgift_info: Optional[str]
    merke: str
    modell: str
    modellår: int
    karosseri: str
    drivstoff: str
    effekt_hk: int
    kilometerstand_km: int
    batterikapasitet_kWh: int
    rekkevidde_km: int
    girkasse: str
    maksimal_tilhengervekt_kg: int
    hjuldrift: str
    vekt_kg: int
    seter: int
    dører: int
    bagasjerom_volum_l: int
    farge: str
    fargebeskrivelse: str
    interiørfarge: str
    bilen_står_i: str
    neste_eu_kontroll: date
    avgiftsklasse: str
    registreringsnummer: str
    chassisnummer: str
    førstegangsregistrert: date
    eiere: int
    garanti: str
    salgsform: str


def parse_car_listing(data: dict) -> CarListing:
    def parse_int(s):
        return int(
            s.replace(" ", "")
            .replace("kr", "")
            .replace("km", "")
            .replace("kg", "")
            .replace("l", "")
            .strip()
        )

    def parse_date(s):
        return datetime.strptime(s.strip(), "%d.%m.%Y")

    return CarListing(
        omregistrering=parse_int(data.get("Omregistrering", "0")),
        pris_eks_omreg=parse_int(data.get("Pris eksl. omreg.", "0")),
        årsavgift_info=data.get("Årsavgift", ""),
        merke=data.get("Merke", ""),
        modell=data.get("Modell", ""),
        modellår=int(data.get("Modellår", "0")),
        karosseri=data.get("Karosseri", ""),
        drivstoff=data.get("Drivstoff", ""),
        effekt_hk=parse_int(data.get("Effekt", "0")),
        kilometerstand_km=parse_int(data.get("Kilometerstand", "0")),
        batterikapasitet_kWh=parse_int(data.get("Batterikapasitet", "0")),
        rekkevidde_km=parse_int(data.get("Rekkevidde (WLTP)", "0")),
        girkasse=data.get("Girkasse", ""),
        maksimal_tilhengervekt_kg=parse_int(data.get("Maksimal tilhengervekt", "0")),
        hjuldrift=data.get("Hjuldift", ""),
        vekt_kg=parse_int(data.get("Vekt", "0")),
        seter=int(data.get("Seter", "0")),
        dører=int(data.get("Dører", "0")),
        bagasjerom_volum_l=parse_int(data.get("Størrelse på bagasjerom", "0")),
        farge=data.get("Farge", ""),
        fargebeskrivelse=data.get("Fargebeskrivelse", ""),
        interiørfarge=data.get("Interiørfarge", ""),
        bilen_står_i=data.get("Bilen står i", ""),
        neste_eu_kontroll=parse_date(data.get("Neste frist for EU-kontroll", "01.01.1900")),
        avgiftsklasse=data.get("Avgiftsklasse", ""),
        registreringsnummer=data.get("Registreringsnummer", ""),
        chassisnummer=data.get("Chassis nr. (VIN)", ""),
        førstegangsregistrert=parse_date(data.get("1. gang registrert", "01.01.1900")),
        eiere=int(data.get("Eiere", "0")),
        garanti=data.get("Garanti", ""),
        salgsform=data.get("Salgsform", "")
    )


def get_ad_data(driver, ad_id):
    # Navigate to the ad page
    driver.get(f"https://www.finn.no/mobility/item/{ad_id}")

    # Wait until the ad title is present
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ad-title")))
    except TimeoutException:
        return None

    # Extract ad data
    try:
        title = driver.find_element(By.CSS_SELECTOR, "h1.ad-title").text
        price = driver.find_element(By.CSS_SELECTOR, "span.price").text
        location = driver.find_element(By.CSS_SELECTOR, "span.location").text
        description = driver.find_element(By.CSS_SELECTOR, "div.description").text
    except NoSuchElementException:
        return None
    
    try:
        specs_parent = driver.find_element(By.CSS_SELECTOR, "dl.emptycheck")
        parsed_data = {}
        for ek, ev in zip(
            specs_parent.find_elements(By.TAG_Name, "dt"),
            specs_parent.find_elements(By.TAG_Name, "dd"),
        ):
            key = ek.text.strip()
            value = ev.text.strip()
            parsed_data[key] = value
    except NoSuchElementException:
        pass

    return {
        "id": ad_id,
        "title": title,
        "price": price,
        "location": location,
        "description": description,
    }



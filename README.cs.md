# Cookeo Bridge — český návod

[English](README.md)

Doplněk pro Home Assistant OS s webovým rozhraním, vlastními soukromými recepty a MQTT entitami pro Cookeo. Funguje také samostatně v Dockeru nebo Pythonu 3.12+.

## Proč vznikl

Hrnec zakoupený pro jiný distribuční trh nemusí být v místní aplikaci dostupný pro registraci a používání. Konkrétně u Cookeo Infinity CE9821F0 s francouzštinou, italštinou a nizozemštinou se nepodařila česká registrace přes My Tefal. Stejný účet výrobce však fungoval v belgickém kontextu My Moulinex.

Doplněk umožňuje nastavit odpovídající značku, zemi a jazyk účtu a používat hrnec přes české nebo anglické webové rozhraní a Home Assistant. Komunikace dál využívá cloud výrobce. Jazyk v menu hrnce zůstává původní; firmware se nemění.

## Instalace

1. V Home Assistant otevři **Nastavení → Aplikace / Doplňky → Obchod → ⋮ → Repozitáře**.
2. Přidej `https://github.com/AidenShaw2020/cookeo-bridge`.
3. Nainstaluj **Cookeo Bridge** a otevři jeho **Konfiguraci**.
4. Pro ověřený belgický CE9821F0 nastav:

```yaml
ui_language: cs
brand: moulinex
country: BE
language: nl
mqtt_host: ""
mqtt_port: 1883
mqtt_username: ""
mqtt_password: ""
mqtt_tls: false
```

5. Spusť doplněk a otevři webové rozhraní. V **Účet a jazyk** se přihlas stejným e-mailem jako dosud. Heslo zadávej pouze na stránce výrobce.
6. MQTT lze převzít ze služby Mosquitto v HA. Případně vyplň přístup k vlastnímu brokeru. V HA musí být nastavená integrace MQTT.

**Již spárovaný hrnec znovu nepáruj.** Po přihlášení ke stejnému účtu a regionu se načte jeho existující cloudová vazba. Volba `language: nl` je jazyk účtu/hrnce; `ui_language: cs` nezávisle nastavuje češtinu doplňku. Zemi Apple ID ani App Storu není potřeba měnit.

Při přechodu z PC nejdřív zastav starý vývojový proces, pak spusť doplněk. Přihlášení v HA můžeš provést znovu; registrace hrnce tím nezanikne. Místní recepty přenes přes **Moje recepty → Export / Import**. Celé soukromé `.dev-data` ani tokeny nikam na GitHub nekopíruj. Samostatné místní poznámky k online receptům nejsou součástí exportu knihovny.

## Recepty a soukromí

- **Uložit**: pouze místní knihovna.
- **Uložit na cloud**: aktuální recept se zvolenou viditelností, výchozí je soukromý.
- **Přiřadit online kuchařku**: otevře výběr pro již nahraný recept. Otevření ani zrušení výběru nic nenahrává a nepublikuje.
- **Odeslat na hrnec**: ověří a odešle aktuální uloženou cloudovou verzi. Neuložené změny nejprve ulož na cloud. Vaření spustíš až na hrnci.

Štítky rozlišují místní kopii, soukromý/veřejný cloudový recept a neuložené změny. Při otevření se stav ověřuje přes API. Autora automaticky určuje přihlášený účet; přezdívka se zobrazuje vpravo nahoře.

U nového receptu je soukromý/veřejný volbou pro první nahrání. U již nahraného receptu přepnutí ihned změní viditelnost jeho autorského základu v cloudu. Osobní kopie `PERSONAL` pro hrnec zůstává soukromá. Veřejná viditelnost je požadavek na publikaci; indexaci a případné schvalování řídí výrobce. Při testování vydání nebyl žádný recept veřejně publikován.

**Omezení mazání:** přesný požadavek DELETE doložený v APK vrátil u našeho soukromého autorského testu HTTP 403. Rozhraní umožňuje pokus o odstranění a výsledek ověřuje. Při odmítnutí nesmaže místní propojený recept ani jeho vazby, aby bylo možné operaci zopakovat. Mazání pouze z cloudu místní obsah ponechá. Místní recept bez propojené cloudové kopie lze smazat běžně.

V editoru lze zadat suroviny, jejich přiřazení ke krokům, programy, časy, teplotu a rychlost míchání podle možností modelu. Soukromé kopie se ověřují i anonymním čtením (očekává se 404), obsah se kontroluje zpětným načtením. Fotografie a poznámky zatím zůstávají místní. Úprava staženého receptu nepřepisuje původní online recept.

Přijetí příkazu cloudem a potvrzení načtení hrncem jsou dvě různé věci. Když automatické potvrzení nepřijde, ověř displej; další pokus se automaticky neposílá.

## Další informace

[Nastavení a přihlášení](cookeo/DOCS.md) · [Testování mimo HA](docs/DEVELOPMENT.md) · [Změny](cookeo/CHANGELOG.md)

Ověřeno na CE9821F0, firmwaru 1.8.3 a My Moulinex BE/nl. Jiné modely a regiony potřebují ověření. Bluetooth proxy HA slouží k vyhledání adresy; samotné nové BLE párování nyní vyžaduje místní Bluetooth adaptér na hostiteli doplňku. Již registrovaný hrnec Bluetooth nepotřebuje.

Licence MIT. Nezávislý komunitní projekt bez spojení s výrobcem; [poděkování a licence převzatých částí](NOTICE.md).

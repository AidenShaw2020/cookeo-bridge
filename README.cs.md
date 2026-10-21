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
- **Uložit na cloud**: vytvoří nebo aktualizuje osobní kopii `PERSONAL`. Při prvním uložení vybereš publikovaný základ ze stejné země a jazyka účtu. Zrušení výběru nic na cloudu nezaloží.
- **Přiřadit online kuchařku**: výběr pro již nahraný recept; otevření ani zrušení nic nenahrává.
- **Odeslat na hrnec**: ověří a odešle aktuální uloženou osobní kopii. Neuložené změny nejprve ulož na cloud. Vaření spustíš až na hrnci.

**Osobní úprava a veřejný autorský recept mají odlišný postup.** Autorský formulář výrobce vyžaduje celý recept a fotografii a soukromou volbu nenabízí. Při živém testu jeho API ignorovalo požadovaný stav `PRIVATE`. Dřívější autorský záznam se soukromým přístupem skončil ve schvalování a ve stavu `TO_BE_CORRECTED`. Anonymní odpověď 404 tedy ověřila omezení přístupu, nikoli vynechání schvalování.

Opravené soukromé ukládání zakládá pouze nativní osobní úpravu `PERSONAL` vybraného publikovaného receptu. Nevytváří ani neaktualizuje autorský záznam a nepřebírá cizí fotografii pokrmu. Původní katalogový recept se nemění. Stejný základ nelze použít pro dvě místní osobní kopie; po ztrátě odpovědi se další kopie automaticky nezakládá. **Živý test BE/nl vytvořil jednu kopii PRIVATE + PERSONAL, ověřil suroviny i kroky a našel ji ve vyhledávání osobních receptů s filtrem PERSONAL. Katalogový základ zůstal zachovaný a nevznikl autorský záznam. Zobrazení v oficiální mobilní aplikaci zatím není potvrzené.**

Přepnutí již nahraného receptu na **Veřejný** výslovně odešle autorskou verzi s vlastní fotografií výrobci ke schválení. Osobní kopie pro hrnec zůstává soukromá. Štítek odlišuje čekání na schválení, požadavek na opravu a schválené zveřejnění. Samotné odeslání neznamená okamžitou dostupnost všem. Nový požadavek s fotografií je ověřen testovací odpovědí, nikoli živým veřejným publikováním. Volba **Soukromý** žádá o soukromý přístup k vlastní autorské verzi; nemaže historii schvalování.

Autora určuje přihlášený účet; přezdívka je v horní liště. Poznámky zůstávají místní. Osobní kopie nyní nenahrává místní fotografii. Import přenáší obsah, nikoli vlastnictví původního receptu nebo vazby na existující cloudové kopie. Pro novou osobní kopii zvol dosud neupravený základ, aby nenahradila úpravu z jiné instalace.

**Odebrání z kuchařky je jiná operace než smazání autorského receptu.** Odebrání katalogového receptu ruší pouze jeho zařazení, původní recept zůstává. Smazání kuchařky odstraní kolekci, nikoli původní recepty. Obě operace prošly živým testem v BE/nl. Verze 0.3.1 opravuje odebírání tím, že převádí ID varianty ze seznamu na ID hlavního receptu.

Samostatné smazání našeho soukromého autorského záznamu přes DELETE zatím vrátilo 403. Nejde o obecné omezení účtu pro správu kuchařek. Při odmítnutém smazání propojeného receptu se místní obsah a vazby zachovají pro další pokus.

Přijetí příkazu cloudem a potvrzení načtení hrncem jsou dvě různé věci. Když automatické potvrzení nepřijde, ověř displej; další pokus se automaticky neposílá.

## Další informace

[Nastavení a přihlášení](cookeo/DOCS.md) · [Testování mimo HA](docs/DEVELOPMENT.md) · [Změny](cookeo/CHANGELOG.md)

Ověřeno na CE9821F0, firmwaru 1.8.3 a My Moulinex BE/nl. Jiné modely a regiony potřebují ověření. Bluetooth proxy HA slouží k vyhledání adresy; samotné nové BLE párování nyní vyžaduje místní Bluetooth adaptér na hostiteli doplňku. Již registrovaný hrnec Bluetooth nepotřebuje.

Licence MIT. Nezávislý komunitní projekt bez spojení s výrobcem; [poděkování a licence převzatých částí](NOTICE.md).

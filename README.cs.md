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

## Ruční dokončení přihlášení

Odkaz `gsmoduser://tokens#...` získáš **ze zdrojového kódu návratové stránky výrobce po přihlášení**, nikoli z adresního řádku prohlížeče.

1. Na návratové stránce otevři **Zobrazit zdrojový kód stránky** (na PC `Ctrl+U`).
2. Přes `Ctrl+F` najdi `gsmoduser://tokens#` a zkopíruj celý odkaz včetně části za `#`, bez okolních uvozovek.
3. V doplňku otevři **Účet a jazyk → Dokončit návrat z prohlížeče**, vlož ho do pole **Návratový odkaz** a ulož.

Běžná `https://account.groupeseb.com/...` adresa nefunguje. Odkaz obsahuje přihlašovací tokeny; nikam ho neposílej.

## Autorské recepty a osobní úpravy

Knihovna rozlišuje **Autorský recept** vytvořený od nuly a **Osobní úpravu** importovaného online receptu. Označení je na kartě, v detailu i editoru. Import zachovává název a autora originálu i odkaz na něj; upravenou kopii nelze přejmenováním typu vydávat za samostatný autorský recept. Původ se zachovává při úpravách i JSON exportu/importu.

### Import online receptu

1. V **Online receptech** otevři recept a zvol **Uložit kopii do knihovny**.
2. Uprav si suroviny, kroky, porce a časy. **Uložit** ukládá pouze místně.
3. **Uložit osobní úpravu** uloží soukromou variantu `PERSONAL` automaticky navázanou na importovaný originál. Žádný další základ nehledáš; katalogový originál se nemění. Požadavek zachovává původní zemi/jazyk receptu. Jiné kombinace regionů může výrobce odmítnout a zatím nejsou živě ověřené.
4. **Odeslat na hrnec** přenese aktuální ověřenou osobní kopii do volného hrnce. Neodesílá neuložené změny a nespouští vaření. **Přiřadit online kuchařku** otevírá výběr pro už nahranou kopii; zrušení nic nenahrává.

Osobní úprava se neposílá do toku nového autorského receptu. Vlastníkem místní kopie je přihlášený účet; původní autor je zobrazený zvlášť. Poznámky zůstávají místní.

### Nový recept od nuly

1. Zvol **Nový recept** a napiš vlastní název, suroviny a kroky včetně programů hrnce. Můžeš ho uložit jako místní koncept. Žádný cizí základ se nevybírá.
2. Přidej vlastní fotografii hotového pokrmu a klikni na **Zkontrolovat a publikovat**.
3. Náhled vypíše chybějící požadavky podle formuláře výrobce: fotografie, podporovaný typ jídla, 1–99 porcí, příprava alespoň 1 minutu, suroviny přiřazené ke krokům, číselné množství v povoleném rozsahu, popis každého kroku do 1000 znaků a alespoň jeden program hrnce. Parametry se ověřují podle modelu. Součástí jsou pokyny pro fotografii a odkaz na podmínky výrobce.
4. Zkontroluj obsah a výslovně potvrď odeslání. Otevření ani zrušení náhledu nic nepublikuje. Výrobce recept může schválit nebo vrátit k opravě; odeslání neznamená okamžité zveřejnění všem.

Po potvrzení autorského záznamu se odděleně připravuje soukromá kopie `PERSONAL` pro hrnec, navázaná na **tento vlastní autorský záznam**, nikoli na cizí recept. Schvalování a připravenost kopie pro hrnec jsou různé stavy. Přenos je dostupný až po ověření osobní kopie. Pokud výrobce přijme autorský recept, ale jeho osobní varianta zatím není dostupná, doplněk to uvede a zachová již získané ID místo založení dalšího autorského záznamu.

Štítky rozlišují soukromý přístup, čekání na schválení, požadavek na opravu a schválené zveřejnění. U odeslané autorské verze lze požádat o soukromou viditelnost; opětovná veřejná volba otevře publikační náhled. Historie schvalování tím nezaniká. Po ztrátě odpovědi na vytvoření se nový záznam automaticky nezakládá. Selhání nahrání fotografie před založením receptu lze opakovat.

**Ověření:** soukromé založení, čtení a smazání PERSONAL prošlo živým testem BE/nl; dříve byl ověřen i přenos do hrnce. Nový celý autorský postup včetně fotografie, aktualizace a přípravy osobní kopie je ověřen náhradními odpověďmi backendu a testy rozhraní. Žádný nový syntetický recept jsme veřejně neodesílali. Zobrazení v originální mobilní aplikaci a schválení výrobcem zatím potvrzené nejsou. Dřívější autorský záznam s přístupem PRIVATE prošel moderací; soukromá viditelnost ani anonymní 404 nejsou důkazem vynechání schvalování.

**Odebrání z kuchařky je jiná operace než smazání autorského receptu.** Odebrání katalogového receptu ruší pouze jeho zařazení, původní recept zůstává. Smazání kuchařky odstraní kolekci, nikoli původní recepty. Obě operace prošly živým testem v BE/nl. Verze 0.3.1 opravuje odebírání tím, že převádí ID varianty ze seznamu na ID hlavního receptu.

Smazání osobní kopie `PERSONAL` je živě ověřené v BE/nl. Cloud zachová evidenční záznam `DELETED`, ale rozhraní mobilní aplikace vrací 404 a recept zmizí z osobního seznamu. Verze 0.3.2 tento výsledek správně rozpoznává a při opakování neposílá další DELETE. Místní recept i katalogový základ zůstaly zachované. Jde o logické smazání u výrobce, nikoli důkaz fyzického vymazání jeho dat.

Samostatné smazání našeho soukromého autorského záznamu přes DELETE zatím vrátilo 403. Nejde o obecné omezení účtu pro správu kuchařek. Při odmítnutém smazání propojeného receptu se místní obsah a vazby zachovají pro další pokus.

Přijetí příkazu cloudem a potvrzení načtení hrncem jsou dvě různé věci. Když automatické potvrzení nepřijde, ověř displej; další pokus se automaticky neposílá.

## Další informace

[Nastavení a přihlášení](cookeo/DOCS.md) · [Testování mimo HA](docs/DEVELOPMENT.md) · [Změny](cookeo/CHANGELOG.md)

Ověřeno na CE9821F0, firmwaru 1.8.3 a My Moulinex BE/nl. Jiné modely a regiony potřebují ověření. Bluetooth proxy HA slouží k vyhledání adresy; samotné nové BLE párování nyní vyžaduje místní Bluetooth adaptér na hostiteli doplňku. Již registrovaný hrnec Bluetooth nepotřebuje.

Licence MIT. Nezávislý komunitní projekt bez spojení s výrobcem; [poděkování a licence převzatých částí](NOTICE.md).

### Jazyk hodnot entit

Program, stav vaření a režim se zobrazují podle jazyka rozhraní doplňku. Například `cooking` → „Probíhá vaření“ a `manual` → „Ruční“. Při změně jazyka se hodnoty obnoví při dalším zveřejnění stavu (nejpozději během přibližně 30 sekund při připojení).

Od verze 0.4.5 používej pro automatizace stavových entit raději jejich atribut `code` (`cooking`, `manual` atd.), aby nezávisely na jazyku. Pokud už automatizace porovnává přímo anglický stav entity, je potřeba ji upravit. Původní pole `status` a `mode` v MQTT zprávě zůstávají stejné.

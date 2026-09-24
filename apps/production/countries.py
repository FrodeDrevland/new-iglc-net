"""Country names, for counting papers per country from affiliation texts."""

COUNTRIES = """Afghanistan|Albania|Algeria|Andorra|Angola|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahrain|
Bangladesh|Belarus|Belgium|Benin|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Brazil|Brunei|Bulgaria|
Burkina Faso|Cambodia|Cameroon|Canada|Chile|China|Colombia|Costa Rica|Croatia|Cuba|Cyprus|Czech Republic|
Denmark|Dominican Republic|Ecuador|Egypt|El Salvador|Estonia|Ethiopia|Fiji|Finland|France|Georgia|Germany|Ghana|
Greece|Guatemala|Honduras|Hong Kong|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Israel|Italy|Ivory Coast|
Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kuwait|Latvia|Lebanon|Libya|Lithuania|Luxembourg|Macao|Malawi|Malaysia|
Malta|Mexico|Moldova|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nepal|Netherlands|New Zealand|
Nicaragua|Nigeria|North Macedonia|Norway|Oman|Pakistan|Palestine|Panama|Paraguay|Peru|Philippines|Poland|
Portugal|Qatar|Romania|Russia|Rwanda|Saudi Arabia|Senegal|Serbia|Singapore|Slovakia|Slovenia|South Africa|
South Korea|Spain|Sri Lanka|Sudan|Sweden|Switzerland|Syria|Taiwan|Tanzania|Thailand|Tunisia|Turkey|Uganda|Ukraine|
United Arab Emirates|United Kingdom|Uruguay|USA|Uzbekistan|Venezuela|Vietnam|Zambia|Zimbabwe""".replace("\n", "").split("|")

ALIASES = {
    "united states": "USA", "united states of america": "USA", "u.s.a": "USA", "u.s": "USA", "us": "USA",
    "uk": "United Kingdom", "u.k": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom", "great britain": "United Kingdom",
    "brasil": "Brazil", "perú": "Peru", "méxico": "Mexico", "the netherlands": "Netherlands", "holland": "Netherlands",
    "uae": "United Arab Emirates", "korea": "South Korea", "republic of korea": "South Korea",
    "türkiye": "Turkey", "turkiye": "Turkey", "czechia": "Czech Republic", "deutschland": "Germany",
    "españa": "Spain", "p.r. china": "China", "prc": "China", "people's republic of china": "China",
    "hong kong sar": "Hong Kong", "viet nam": "Vietnam", "russian federation": "Russia", "côte d'ivoire": "Ivory Coast",
}

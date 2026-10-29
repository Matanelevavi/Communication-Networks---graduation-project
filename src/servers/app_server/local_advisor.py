"""
Clothing advice derived from the forecast itself, with no external service.

The AI advisor writes nicer prose, but it needs a key and it can fail. This one
always works, is instant, and is genuinely personalised: it reads the real
temperatures, the hours rain is expected and the swing across the day, and then
says something different for a baby than for an adult.

It writes in English or in Hebrew, following whichever the user typed: a
Hebrew city or a Hebrew name gets a Hebrew paragraph.

It is the default path, not a placeholder.
"""
from src.servers.app_server.external_service import ExternalService
from src.servers.app_server.weather_api import Forecast

ENGLISH = "en"
HEBREW = "he"

# Temperature bands, in Celsius, and what to wear in each.
BANDS = (
    (5, "freezing", "a heavy coat, a hat and gloves"),
    (12, "cold", "a warm coat and long sleeves"),
    (18, "cool", "a jacket or a thick jumper"),
    (24, "mild", "light layers, a long sleeve top is enough"),
    (30, "warm", "light clothes, short sleeves"),
    (99, "hot", "the lightest clothes you have, and a hat"),
)

# The same bands in Hebrew, in the same order.
HEBREW_BANDS = (
    ("קפוא", "מעיל כבד, כובע וכפפות"),
    ("קר", "מעיל חם ושרוולים ארוכים"),
    ("קריר", "ז'קט או סוודר עבה"),
    ("נעים", "שכבות קלות, חולצה ארוכה מספיקה"),
    ("חמים", "בגדים קלים ושרוולים קצרים"),
    ("חם", "הבגדים הכי קלים שיש, וכובע"),
)

# Every sentence the advisor can write, in both languages.
PHRASES = {
    ENGLISH: {
        "headline": "{place} is {word} today, {low}° to {high}°, so go with {clothing}.",
        "rain": "Rain is likely from around {hour}, so take a waterproof layer or an umbrella.",
        "swing": "It drops to {low}° later, which is {word}, "
                 "so bring something to put on for the evening.",
        "sun": "With that much sun, water and a hat are worth taking along.",
        "baby": "For {name}, add one more layer than you would wear yourself.",
        "baby_sun": "For {name}, add one more layer than you would wear yourself, "
                    "and keep the pram out of direct sun.",
        "child": "{name} will be moving about, so something light "
                 "underneath a layer that comes off easily works best.",
        "adult": "{name} can go with the same, adjusted to taste.",
        "spare": " Worth packing a spare set for {notes}.",
        "everyone": "everyone",
        "headline_here": "It is {word} today, {low}° to {high}°, so go with {clothing}.",
        "uv": "The UV index peaks at {uv} today, so sunscreen and a hat matter.",
        "wind": "It is windy, up to {wind} km/h, so a windproof layer will help.",
        "feels": "It feels like {feels}° right now.",
    },
    HEBREW: {
        "headline": "ב{place} {word} היום, {low}° עד {high}°, אז כדאי ללבוש {clothing}.",
        "rain": "צפוי גשם החל מבערך {hour}, אז כדאי לקחת מעיל גשם או מטרייה.",
        "swing": "בהמשך היום יורד ל-{low}°, שזה {word}, אז כדאי לקחת משהו לערב.",
        "sun": "עם כל כך הרבה שמש, כדאי לקחת מים וכובע.",
        "baby": "ל{name} כדאי להוסיף שכבה אחת יותר ממה שאתם לובשים.",
        "baby_sun": "ל{name} כדאי להוסיף שכבה אחת יותר ממה שאתם לובשים, "
                    "ולהרחיק את העגלה משמש ישירה.",
        "child": "{name} יזוז הרבה, אז עדיף משהו קל מתחת לשכבה שקל להוריד.",
        "adult": "{name} יכול להתלבש אותו דבר, לפי הטעם.",
        "spare": " כדאי לארוז סט בגדים להחלפה עבור {notes}.",
        "everyone": "כולם",
        "headline_here": "{word} היום, {low}° עד {high}°, אז כדאי ללבוש {clothing}.",
        "uv": "מדד ה-UV מגיע היום ל-{uv}, אז קרם הגנה וכובע חשובים.",
        "wind": "יש רוח, עד {wind} קמ\"ש, אז שכבה שחוסמת רוח תעזור.",
        "feels": "זה מרגיש כמו {feels}° כרגע.",
    },
}

STRONG_UV = 6           # the index from which sun protection is called for
WINDY_FROM = 30         # km/h
FEELS_DIFFERENT = 4     # degrees between the air and how it feels before it is worth saying

BIG_SWING = 10          # degrees between low and high that call for a layer
STRONG_SUN = 27         # above this, sun protection is worth mentioning

# How the age of a person may be written, in English or in Hebrew.
BABY_WORDS = {"baby", "infant", "toddler", "תינוק", "תינוקת", "פעוט", "פעוטה"}
CHILD_WORDS = {"child", "kid", "ילד", "ילדה"}


class LocalAdvisor:
    """Builds a recommendation paragraph from the numbers in a forecast."""

    def recommend(self, forecast: Forecast, profiles, language: str | None = None) -> str:
        # The page says which language it is shown in, which is a better guide
        # than guessing from a city typed in English by someone reading Hebrew.
        language = language if language in PHRASES else self.language_of(forecast, profiles)
        say = PHRASES[language]

        parts = [self._headline(forecast, language)]

        rain = self._rain(forecast, language)
        if rain:
            parts.append(rain)

        swing = self._swing(forecast, language)
        if swing:
            parts.append(swing)

        parts.extend(self._conditions(forecast, language))

        parts.extend(self._per_person(forecast, profiles, language))

        if forecast.max_temp >= STRONG_SUN:
            parts.append(say["sun"])

        return " ".join(parts)

    @staticmethod
    def language_of(forecast: Forecast, profiles) -> str:
        """Hebrew when the user wrote any of the city or the family in Hebrew."""
        typed = f"{forecast.place.name} {profiles or ''}"
        return ENGLISH if ExternalService.is_english_only(typed) else HEBREW

    # ------------------------------------------------------------ the day
    @staticmethod
    def band(temperature: float, language: str = ENGLISH) -> tuple[str, str]:
        """The word for a temperature, and what it calls for."""
        index = next((i for i, (ceiling, _w, _c) in enumerate(BANDS)
                      if temperature < ceiling), len(BANDS) - 1)
        if language == HEBREW:
            return HEBREW_BANDS[index]
        return BANDS[index][1], BANDS[index][2]

    def _headline(self, forecast: Forecast, language: str) -> str:
        word, clothing = self.band(forecast.max_temp, language)
        # A place shared by the browser has no name, so the sentence is about "today".
        key = "headline" if forecast.place.name else "headline_here"
        place = forecast.place.name
        # Hebrew glues "in" to the name ("באריאל"); a name in Latin letters
        # takes a hyphen, or the prefix runs into it ("בHaifa").
        if language == HEBREW and place and ExternalService.is_english_only(place[0]):
            place = f"-{place}"
        return PHRASES[language][key].format(
            place=place, word=word, clothing=clothing,
            low=f"{forecast.min_temp:g}", high=f"{forecast.max_temp:g}")

    def _conditions(self, forecast: Forecast, language: str) -> list[str]:
        """What the temperature alone does not say: sun, wind and how it feels."""
        say = PHRASES[language]
        notes = []
        if (forecast.feels_like is not None and forecast.current_temp is not None
                and abs(forecast.feels_like - forecast.current_temp) >= FEELS_DIFFERENT):
            notes.append(say["feels"].format(feels=f"{forecast.feels_like:g}"))

        wind = forecast.peak_wind_kmh
        if wind >= WINDY_FROM:
            notes.append(say["wind"].format(wind=f"{wind:.0f}"))

        if (forecast.uv_max or 0) >= STRONG_UV:
            notes.append(say["uv"].format(uv=f"{forecast.uv_max:.0f}"))
        return notes

    @staticmethod
    def _rain(forecast: Forecast, language: str) -> str:
        if forecast.rain_summary == "No rain expected":
            return ""
        first_hour = forecast.rain_summary.split(" ")[0]
        return PHRASES[language]["rain"].format(hour=first_hour)

    def _swing(self, forecast: Forecast, language: str) -> str:
        if forecast.max_temp - forecast.min_temp < BIG_SWING:
            return ""
        evening_word, _ = self.band(forecast.min_temp, language)
        return PHRASES[language]["swing"].format(
            low=f"{forecast.min_temp:g}", word=evening_word)

    # --------------------------------------------------------- the people
    def _per_person(self, forecast: Forecast, profiles, language: str) -> list[str]:
        """One sentence for anyone who needs different treatment from an adult."""
        notes = []
        for profile in profiles or []:
            if not isinstance(profile, dict):
                continue
            sentence = self._for_profile(forecast, profile, language)
            if sentence:
                notes.append(sentence)
        return notes

    def _for_profile(self, forecast: Forecast, profile: dict, language: str) -> str:
        say = PHRASES[language]
        name = str(profile.get("name", "")).strip() or say["everyone"]
        age = str(profile.get("age_category", "")).strip().lower()
        extra = str(profile.get("notes", "")).strip()

        if age in BABY_WORDS:
            key = "baby_sun" if forecast.max_temp >= STRONG_SUN else "baby"
            advice = say[key].format(name=name)
        elif age in CHILD_WORDS:
            advice = say["child"].format(name=name)
        else:
            return say["adult"].format(name=name) if extra else ""

        if extra:
            advice += say["spare"].format(notes=extra.lower())
        return advice

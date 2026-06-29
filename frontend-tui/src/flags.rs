use std::collections::HashMap;
use std::sync::OnceLock;

static FLAG_MAP: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();

fn flag_map() -> &'static HashMap<&'static str, &'static str> {
    FLAG_MAP.get_or_init(|| {
        let mut m = HashMap::new();
        m.insert("Algeria", "🇩🇿");
        m.insert("Argentina", "🇦🇷");
        m.insert("Australia", "🇦🇺");
        m.insert("Austria", "🇦🇹");
        m.insert("Belgium", "🇧🇪");
        m.insert("Bosnia and Herzegovina", "🇧🇦");
        m.insert("Brazil", "🇧🇷");
        m.insert("Canada", "🇨🇦");
        m.insert("Cape Verde", "🇨🇻");
        m.insert("Colombia", "🇨🇴");
        m.insert("Croatia", "🇭🇷");
        m.insert("Curacao", "🇨🇼");
        m.insert("Czechia", "🇨🇿");
        m.insert("DR Congo", "🇨🇩");
        m.insert("Ecuador", "🇪🇨");
        m.insert("Egypt", "🇪🇬");
        m.insert("England", "🏴");
        m.insert("France", "🇫🇷");
        m.insert("Germany", "🇩🇪");
        m.insert("Ghana", "🇬🇭");
        m.insert("Haiti", "🇭🇹");
        m.insert("Iran", "🇮🇷");
        m.insert("Iraq", "🇮🇶");
        m.insert("Ivory Coast", "🇨🇮");
        m.insert("Japan", "🇯🇵");
        m.insert("Jordan", "🇯🇴");
        m.insert("Mexico", "🇲🇽");
        m.insert("Morocco", "🇲🇦");
        m.insert("Netherlands", "🇳🇱");
        m.insert("New Zealand", "🇳🇿");
        m.insert("Norway", "🇳🇴");
        m.insert("Panama", "🇵🇦");
        m.insert("Paraguay", "🇵🇾");
        m.insert("Portugal", "🇵🇹");
        m.insert("Qatar", "🇶🇦");
        m.insert("Saudi Arabia", "🇸🇦");
        m.insert("Scotland", "🏴");
        m.insert("Senegal", "🇸🇳");
        m.insert("South Africa", "🇿🇦");
        m.insert("South Korea", "🇰🇷");
        m.insert("Spain", "🇪🇸");
        m.insert("Sweden", "🇸🇪");
        m.insert("Switzerland", "🇨🇭");
        m.insert("Tunisia", "🇹🇳");
        m.insert("Turkiye", "🇹🇷");
        m.insert("Uruguay", "🇺🇾");
        m.insert("USA", "🇺🇸");
        m.insert("Uzbekistan", "🇺🇿");
        m
    })
}

pub fn flag_for(team: &str) -> &'static str {
    match flag_map().get(team) {
        Some(flag) => flag,
        None => {
            eprintln!("[flags] WARNING: no flag mapping for team: {:?}", team);
            "🏳️"
        }
    }
}

pub fn confederation_for(team: &str) -> &'static str {
    match team {
        "Algeria" | "Cape Verde" | "DR Congo" | "Egypt" | "Ghana" | "Ivory Coast" | "Morocco"
        | "Senegal" | "South Africa" | "Tunisia" => "CAF",
        "Argentina" | "Brazil" | "Colombia" | "Ecuador" | "Paraguay" | "Uruguay" => "CONMEBOL",
        "Australia" | "Iran" | "Iraq" | "Japan" | "Jordan" | "Qatar" | "Saudi Arabia"
        | "South Korea" | "Uzbekistan" => "AFC",
        "Canada" | "Curacao" | "Haiti" | "Mexico" | "Panama" | "USA" => "CONCACAF",
        "New Zealand" => "OFC",
        _ => "UEFA",
    }
}

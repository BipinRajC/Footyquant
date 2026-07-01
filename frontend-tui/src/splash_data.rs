use crate::flags;
use chrono::{DateTime, Utc};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct NextMatch {
    pub home_team: String,
    pub away_team: String,
    pub stage: String,
    pub match_date: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct TeamInfo {
    pub name: String,
    pub flag: &'static str,
    pub confederation: &'static str,
}

impl TeamInfo {
    pub fn from_name(name: &str) -> Self {
        Self {
            name: name.to_string(),
            flag: flags::flag_for(name),
            confederation: flags::confederation_for(name),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct NextMatchRow {
    home_team: String,
    away_team: String,
    stage: String,
    match_date: DateTime<Utc>,
}

impl From<NextMatchRow> for NextMatch {
    fn from(row: NextMatchRow) -> Self {
        Self {
            home_team: row.home_team,
            away_team: row.away_team,
            stage: row.stage,
            match_date: row.match_date,
        }
    }
}

pub fn next_match_query() -> &'static str {
    "is_played=eq.false&order=match_date.asc&limit=1&select=home_team,away_team,stage,match_date"
}

#[derive(Debug, Clone, Deserialize)]
pub struct AliveTeamRow {
    pub home_team: String,
    pub away_team: String,
    pub result_1x2: Option<String>,
}

pub fn alive_teams_query() -> &'static str {
    "is_knockout=eq.true&select=home_team,away_team,result_1x2"
}

pub const WC_FACTS: &[&str] = &[
    "Brazil has won 5 World Cups, more than any other nation.",
    "The 2026 World Cup is the first to feature 48 teams and 104 matches.",
    "Only 8 teams have ever won the World Cup since 1930.",
    "Germany and Italy have each won 4 World Cup titles.",
    "The fastest goal in World Cup history was scored in 11 seconds by Hakan Sukur (2002).",
    "Mexico has hosted the World Cup 3 times, more than any other country.",
    "The World Cup trophy is made of 18-carat gold and weighs 6.1 kg.",
    "Just Fontaine scored 13 goals in a single World Cup (1958), a record still standing.",
    "The 2026 World Cup is co-hosted by USA, Canada, and Mexico across 16 cities.",
    "Only 2 non-European teams have won a World Cup on European soil: Brazil (1958) and Argentina (1986).",
    "The youngest scorer in World Cup history was Pele at 17 years and 239 days.",
    "Italy failed to qualify for both the 2018 and 2022 World Cups.",
];

pub fn fact_for_index(index: usize) -> &'static str {
    WC_FACTS[index % WC_FACTS.len()]
}

pub fn format_countdown(target: DateTime<Utc>, now: DateTime<Utc>) -> String {
    let delta = target.signed_duration_since(now);
    if delta.num_seconds() <= 0 {
        return "LIVE NOW".to_string();
    }
    let total_secs = delta.num_seconds();
    let days = total_secs / 86400;
    let hours = (total_secs % 86400) / 3600;
    let mins = (total_secs % 3600) / 60;
    let secs = total_secs % 60;
    format!("{:02}d {:02}h {:02}m {:02}s", days, hours, mins, secs)
}

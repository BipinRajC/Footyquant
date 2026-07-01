use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct BracketSlot {
    pub slot_id: &'static str,
    pub round: &'static str,
    pub teams: [&'static str; 2],
    pub winner_to: Option<&'static str>,
    pub loser_to: Option<&'static str>,
}

fn build_bracket() -> Vec<BracketSlot> {
    vec![
        // Round of 32
        BracketSlot {
            slot_id: "R32_1",
            round: "R32",
            teams: ["Germany", "Paraguay"],
            winner_to: Some("R16_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_2",
            round: "R32",
            teams: ["France", "Sweden"],
            winner_to: Some("R16_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_3",
            round: "R32",
            teams: ["South Africa", "Canada"],
            winner_to: Some("R16_2"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_4",
            round: "R32",
            teams: ["Netherlands", "Morocco"],
            winner_to: Some("R16_2"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_5",
            round: "R32",
            teams: ["Portugal", "Croatia"],
            winner_to: Some("R16_3"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_6",
            round: "R32",
            teams: ["Spain", "Austria"],
            winner_to: Some("R16_3"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_7",
            round: "R32",
            teams: ["USA", "Bosnia and Herzegovina"],
            winner_to: Some("R16_4"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_8",
            round: "R32",
            teams: ["Belgium", "Senegal"],
            winner_to: Some("R16_4"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_9",
            round: "R32",
            teams: ["Brazil", "Japan"],
            winner_to: Some("R16_5"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_10",
            round: "R32",
            teams: ["Ivory Coast", "Norway"],
            winner_to: Some("R16_5"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_11",
            round: "R32",
            teams: ["Mexico", "Ecuador"],
            winner_to: Some("R16_6"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_12",
            round: "R32",
            teams: ["England", "DR Congo"],
            winner_to: Some("R16_6"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_13",
            round: "R32",
            teams: ["Argentina", "Cape Verde"],
            winner_to: Some("R16_7"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_14",
            round: "R32",
            teams: ["Australia", "Egypt"],
            winner_to: Some("R16_7"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_15",
            round: "R32",
            teams: ["Switzerland", "Algeria"],
            winner_to: Some("R16_8"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R32_16",
            round: "R32",
            teams: ["Colombia", "Ghana"],
            winner_to: Some("R16_8"),
            loser_to: None,
        },
        // Round of 16
        BracketSlot {
            slot_id: "R16_1",
            round: "R16",
            teams: ["Winner(R32_1)", "Winner(R32_2)"],
            winner_to: Some("QF_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_2",
            round: "R16",
            teams: ["Winner(R32_3)", "Winner(R32_4)"],
            winner_to: Some("QF_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_3",
            round: "R16",
            teams: ["Winner(R32_5)", "Winner(R32_6)"],
            winner_to: Some("QF_2"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_4",
            round: "R16",
            teams: ["Winner(R32_7)", "Winner(R32_8)"],
            winner_to: Some("QF_2"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_5",
            round: "R16",
            teams: ["Winner(R32_9)", "Winner(R32_10)"],
            winner_to: Some("QF_3"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_6",
            round: "R16",
            teams: ["Winner(R32_11)", "Winner(R32_12)"],
            winner_to: Some("QF_3"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_7",
            round: "R16",
            teams: ["Winner(R32_13)", "Winner(R32_14)"],
            winner_to: Some("QF_4"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "R16_8",
            round: "R16",
            teams: ["Winner(R32_15)", "Winner(R32_16)"],
            winner_to: Some("QF_4"),
            loser_to: None,
        },
        // Quarterfinals
        BracketSlot {
            slot_id: "QF_1",
            round: "QF",
            teams: ["Winner(R16_1)", "Winner(R16_2)"],
            winner_to: Some("SF_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "QF_2",
            round: "QF",
            teams: ["Winner(R16_3)", "Winner(R16_4)"],
            winner_to: Some("SF_1"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "QF_3",
            round: "QF",
            teams: ["Winner(R16_5)", "Winner(R16_6)"],
            winner_to: Some("SF_2"),
            loser_to: None,
        },
        BracketSlot {
            slot_id: "QF_4",
            round: "QF",
            teams: ["Winner(R16_7)", "Winner(R16_8)"],
            winner_to: Some("SF_2"),
            loser_to: None,
        },
        // Semifinals
        BracketSlot {
            slot_id: "SF_1",
            round: "SF",
            teams: ["Winner(QF_1)", "Winner(QF_2)"],
            winner_to: Some("FINAL"),
            loser_to: Some("THIRD_PLACE"),
        },
        BracketSlot {
            slot_id: "SF_2",
            round: "SF",
            teams: ["Winner(QF_3)", "Winner(QF_4)"],
            winner_to: Some("FINAL"),
            loser_to: Some("THIRD_PLACE"),
        },
        // Third Place
        BracketSlot {
            slot_id: "THIRD_PLACE",
            round: "3rd",
            teams: ["Loser(SF_1)", "Loser(SF_2)"],
            winner_to: None,
            loser_to: None,
        },
        // Final
        BracketSlot {
            slot_id: "FINAL",
            round: "Final",
            teams: ["Winner(SF_1)", "Winner(SF_2)"],
            winner_to: None,
            loser_to: None,
        },
    ]
}

pub struct MatchContext {
    pub current_round: String,
    pub next_opponent: String,
    pub next_round_name: String,
    pub path_to_final: String,
    pub bracket_side: String,
}

pub fn get_match_context(
    home_team: &str,
    away_team: &str,
    completed: &[crate::timeline::CompletedMatchRow],
) -> MatchContext {
    let bracket = build_bracket();
    let slot = bracket.iter().find(|s| {
        (s.teams[0] == home_team && s.teams[1] == away_team)
            || (s.teams[0] == away_team && s.teams[1] == home_team)
    });

    let slot = match slot {
        Some(s) => s,
        None => {
            return MatchContext {
                current_round: "Knockout".to_string(),
                next_opponent: "TBD".to_string(),
                next_round_name: "next round".to_string(),
                path_to_final: "Knockout Stage".to_string(),
                bracket_side: "Main Bracket".to_string(),
            };
        }
    };

    let winner_map = build_winner_map(completed, &bracket);
    let current_round = slot.round.to_string();
    let next_slot_id = slot.winner_to.unwrap_or("");
    let path = build_path(next_slot_id, &bracket);

    let (next_opponent, next_round_name) = if next_slot_id.is_empty() {
        ("—".to_string(), "—".to_string())
    } else {
        let next_slot = bracket.iter().find(|s| s.slot_id == next_slot_id);
        match next_slot {
            Some(ns) => {
                let resolved: Vec<String> = ns
                    .teams
                    .iter()
                    .map(|t| resolve_team(t, &winner_map))
                    .collect();
                let opponent = resolved.join(" vs ");
                (opponent, ns.round.to_string())
            }
            None => ("TBD".to_string(), "next round".to_string()),
        }
    };

    let bracket_side = match slot.slot_id {
        s if s.ends_with('_') && s[s.len() - 1..].parse::<u32>().unwrap_or(0) <= 4 => "Upper Half",
        _ => "Lower Half",
    };

    MatchContext {
        current_round,
        next_opponent,
        next_round_name,
        path_to_final: path,
        bracket_side: bracket_side.to_string(),
    }
}

fn build_winner_map(
    completed: &[crate::timeline::CompletedMatchRow],
    bracket: &[BracketSlot],
) -> HashMap<String, String> {
    let mut map: HashMap<String, String> = HashMap::new();

    for row in completed {
        let winner = if row.result_1x2 == "H" {
            row.home_team.clone()
        } else {
            row.away_team.clone()
        };

        if let Some(slot) = bracket.iter().find(|s| {
            (s.teams[0] == row.home_team && s.teams[1] == row.away_team)
                || (s.teams[0] == row.away_team && s.teams[1] == row.home_team)
        }) {
            map.insert(slot.slot_id.to_string(), winner);
        }
    }

    for slot in bracket.iter().filter(|s| s.round != "R32") {
        let resolved: Vec<String> = slot.teams.iter().map(|t| resolve_team(t, &map)).collect();
        let all_resolved = resolved
            .iter()
            .all(|r| !r.starts_with("Winner(") && !r.starts_with("Loser("));
        if all_resolved {
            if let Some(ws) = slot.winner_to {
                map.insert(slot.slot_id.to_string(), "TBD".to_string());
            }
        }
    }

    map
}

fn resolve_team(team: &str, winner_map: &HashMap<String, String>) -> String {
    if let Some(inner) = team
        .strip_prefix("Winner(")
        .and_then(|s| s.strip_suffix(')'))
    {
        winner_map
            .get(inner)
            .cloned()
            .unwrap_or_else(|| team.to_string())
    } else if let Some(inner) = team
        .strip_prefix("Loser(")
        .and_then(|s| s.strip_suffix(')'))
    {
        winner_map
            .get(inner)
            .cloned()
            .unwrap_or_else(|| team.to_string())
    } else {
        team.to_string()
    }
}

fn build_path(next_slot_id: &str, bracket: &[BracketSlot]) -> String {
    let mut path = Vec::new();
    let mut current = next_slot_id;

    loop {
        let slot = match bracket.iter().find(|s| s.slot_id == current) {
            Some(s) => s,
            None => break,
        };
        path.push(slot.round);
        match slot.winner_to {
            Some(next) => current = next,
            None => break,
        }
    }

    if path.is_empty() {
        return "Knockout Stage".to_string();
    }

    let mut result = String::new();
    for (i, round) in path.iter().enumerate() {
        if i > 0 {
            result.push_str(" \u{2192} ");
        }
        result.push_str(round);
    }
    result
}

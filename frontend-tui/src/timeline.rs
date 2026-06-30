use crate::models::MatchPrediction;
use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Verdict {
    Correct,
    Partial,
    Wrong,
}

#[derive(Debug, Clone)]
pub enum TimelineEntry {
    Completed {
        match_id: String,
        match_date: String,
        home_team: String,
        away_team: String,
        stage: String,
        group_name: Option<String>,
        home_score: i32,
        away_score: i32,
        result_1x2: String,
        match_outcome: Option<String>,
        aet_home_score: Option<i32>,
        aet_away_score: Option<i32>,
        penalties_home_score: Option<i32>,
        penalties_away_score: Option<i32>,
        aet_home_xg: Option<f64>,
        aet_away_xg: Option<f64>,
        pred_home_qual: Option<f64>,
        pred_away_qual: Option<f64>,
        pred_home: Option<f64>,
        pred_away: Option<f64>,
        pred_draw: Option<f64>,
        extra_time_prob: Option<f64>,
    },
    Upcoming(MatchPrediction),
}

impl TimelineEntry {
    pub fn match_date(&self) -> &str {
        match self {
            TimelineEntry::Completed { match_date, .. } => match_date,
            TimelineEntry::Upcoming(pred) => &pred.match_date,
        }
    }

    pub fn home_team(&self) -> &str {
        match self {
            TimelineEntry::Completed { home_team, .. } => home_team,
            TimelineEntry::Upcoming(pred) => &pred.home_team,
        }
    }

    pub fn away_team(&self) -> &str {
        match self {
            TimelineEntry::Completed { away_team, .. } => away_team,
            TimelineEntry::Upcoming(pred) => &pred.away_team,
        }
    }

    pub fn stage(&self) -> &str {
        match self {
            TimelineEntry::Completed { stage, .. } => stage,
            TimelineEntry::Upcoming(pred) => &pred.stage,
        }
    }

    pub fn group_name(&self) -> Option<&str> {
        match self {
            TimelineEntry::Completed { group_name, .. } => group_name.as_deref(),
            TimelineEntry::Upcoming(pred) => pred.group_name.as_deref(),
        }
    }

    pub fn match_id(&self) -> &str {
        match self {
            TimelineEntry::Completed { match_id, .. } => match_id,
            TimelineEntry::Upcoming(pred) => &pred.match_id,
        }
    }

    pub fn is_completed(&self) -> bool {
        matches!(self, TimelineEntry::Completed { .. })
    }

    pub fn as_prediction(&self) -> Option<&MatchPrediction> {
        match self {
            TimelineEntry::Upcoming(pred) => Some(pred),
            _ => None,
        }
    }

    pub fn model_verdict(&self) -> Option<Verdict> {
        match self {
            TimelineEntry::Completed {
                result_1x2,
                match_outcome,
                pred_home_qual,
                pred_away_qual,
                extra_time_prob,
                ..
            } => {
                let hq = pred_home_qual.as_ref()?;
                let aq = pred_away_qual.as_ref()?;
                let predicted_home = *hq >= *aq;
                let actual_home = result_1x2 == "H";
                let correct = predicted_home == actual_home;
                let went_to_aet = matches!(match_outcome.as_deref(), Some("aet" | "penalties"));
                let predicted_et = extra_time_prob.map_or(false, |p| p > 0.30);

                if correct && !went_to_aet {
                    Some(Verdict::Correct)
                } else if !correct && went_to_aet && predicted_et {
                    Some(Verdict::Partial)
                } else {
                    Some(Verdict::Wrong)
                }
            }
            _ => None,
        }
    }

    pub fn stage_label(&self) -> String {
        stage_label_for(self.match_date(), self.stage(), self.group_name())
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct CompletedMatchRow {
    pub match_id: String,
    pub match_date: String,
    pub home_team: String,
    pub away_team: String,
    pub stage: String,
    pub group_name: Option<String>,
    pub home_score: i32,
    pub away_score: i32,
    pub result_1x2: String,
    pub match_outcome: Option<String>,
    pub aet_home_score: Option<i32>,
    pub aet_away_score: Option<i32>,
    pub penalties_home_score: Option<i32>,
    pub penalties_away_score: Option<i32>,
    pub aet_home_xg: Option<f64>,
    pub aet_away_xg: Option<f64>,
}

pub fn display_name(team: &str) -> String {
    let cleaned = team.replace(" and ", " & ");
    if cleaned.chars().count() > 14 {
        let truncated: String = cleaned.chars().take(13).collect();
        format!("{}{}", truncated, "\u{2026}")
    } else {
        cleaned
    }
}

pub fn stage_label_for(match_date: &str, stage: &str, group_name: Option<&str>) -> String {
    if stage == "knockout" {
        let date_part = if match_date.len() >= 10 {
            &match_date[..10]
        } else {
            return "KO".to_string();
        };
        match date_part {
            d if d >= "2026-06-28" && d <= "2026-07-03" => "R32".to_string(),
            d if d >= "2026-07-04" && d <= "2026-07-08" => "R16".to_string(),
            d if d >= "2026-07-09" && d <= "2026-07-12" => "QF".to_string(),
            d if d >= "2026-07-13" && d <= "2026-07-15" => "SF".to_string(),
            d if d >= "2026-07-16" => "Final".to_string(),
            _ => "KO".to_string(),
        }
    } else {
        format!("Group {}", group_name.unwrap_or("?"))
    }
}

pub fn merge_timeline(
    completed: Vec<CompletedMatchRow>,
    predictions: Vec<MatchPrediction>,
    pred_lookup: &std::collections::HashMap<String, &MatchPrediction>,
) -> Vec<TimelineEntry> {
    let mut entries: Vec<TimelineEntry> = Vec::new();

    let completed_ids: std::collections::HashSet<String> =
        completed.iter().map(|r| r.match_id.clone()).collect();

    for row in completed {
        let pred = pred_lookup.get(&row.match_id).copied();
        entries.push(TimelineEntry::Completed {
            match_id: row.match_id,
            match_date: row.match_date,
            home_team: row.home_team,
            away_team: row.away_team,
            stage: row.stage,
            group_name: row.group_name,
            home_score: row.home_score,
            away_score: row.away_score,
            result_1x2: row.result_1x2,
            match_outcome: row.match_outcome,
            aet_home_score: row.aet_home_score,
            aet_away_score: row.aet_away_score,
            penalties_home_score: row.penalties_home_score,
            penalties_away_score: row.penalties_away_score,
            aet_home_xg: row.aet_home_xg,
            aet_away_xg: row.aet_away_xg,
            pred_home_qual: pred.map(|p| p.home_qualify_prob.unwrap_or(0.0)),
            pred_away_qual: pred.map(|p| p.away_qualify_prob.unwrap_or(0.0)),
            pred_home: pred.map(|p| p.prob_home),
            pred_away: pred.map(|p| p.prob_away),
            pred_draw: pred.map(|p| p.prob_draw),
            extra_time_prob: pred.and_then(|p| p.extra_time_prob),
        });
    }

    entries.sort_by(|a, b| b.match_date().cmp(a.match_date()));

    let mut upcoming: Vec<TimelineEntry> = predictions
        .into_iter()
        .filter(|p| !completed_ids.contains(&p.match_id))
        .map(TimelineEntry::Upcoming)
        .collect();
    upcoming.sort_by(|a, b| a.match_date().cmp(b.match_date()));

    entries.extend(upcoming);
    entries
}

use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct MatchPrediction {
    pub match_id: String,
    pub match_date: String,
    pub home_team: String,
    pub away_team: String,
    pub stage: String,
    pub group_name: Option<String>,
    pub prob_home: f64,
    pub prob_draw: f64,
    pub prob_away: f64,
    pub prob_home_ci: Option<Vec<f64>>,
    pub prob_draw_ci: Option<Vec<f64>>,
    pub prob_away_ci: Option<Vec<f64>>,
    pub confidence_1x2: String,
    pub ah_line: f64,
    pub ah_home_prob: f64,
    pub ah_away_prob: f64,
    pub confidence_ah: String,
    pub over_25_prob: f64,
    pub under_25_prob: f64,
    pub over_25_ci: Option<Vec<f64>>,
    pub under_25_ci: Option<Vec<f64>>,
    pub confidence_ou: String,
    pub btts_yes_prob: f64,
    pub btts_no_prob: f64,
    pub btts_yes_ci: Option<Vec<f64>>,
    pub btts_no_ci: Option<Vec<f64>>,
    pub confidence_btts: String,
    pub dc_home_xg: f64,
    pub dc_away_xg: f64,
    pub dc_top_scorelines: Option<serde_json::Value>,
    pub narrative: String,
    pub model_version: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Scoreline {
    pub scoreline: String,
    pub home_goals: i32,
    pub away_goals: i32,
    pub probability: f64,
}

impl MatchPrediction {
    pub fn scorelines(&self) -> Vec<Scoreline> {
        self.dc_top_scorelines
            .as_ref()
            .and_then(|v| serde_json::from_value::<Vec<Scoreline>>(v.clone()).ok())
            .unwrap_or_default()
    }

    pub fn ci_width_1x2(&self) -> f64 {
        let home_width = self
            .prob_home_ci
            .as_ref()
            .map(|ci| (ci[1] - ci[0]).abs())
            .unwrap_or(1.0);
        let draw_width = self
            .prob_draw_ci
            .as_ref()
            .map(|ci| (ci[1] - ci[0]).abs())
            .unwrap_or(1.0);
        let away_width = self
            .prob_away_ci
            .as_ref()
            .map(|ci| (ci[1] - ci[0]).abs())
            .unwrap_or(1.0);
        home_width.max(draw_width).max(away_width)
    }

    pub fn top_two_gap(&self) -> f64 {
        let mut probs = [self.prob_home, self.prob_draw, self.prob_away];
        probs.sort_by(|a, b| b.partial_cmp(a).unwrap());
        probs[0] - probs[1]
    }

    pub fn max_prob(&self) -> f64 {
        self.prob_home.max(self.prob_draw).max(self.prob_away)
    }

    pub fn favorite_label(&self) -> &str {
        if self.prob_home == self.max_prob() {
            "home"
        } else if self.prob_away == self.max_prob() {
            "away"
        } else {
            "draw"
        }
    }

    pub fn character_label(&self) -> &'static str {
        if self.max_prob() > 0.65 {
            "CLEAR FAVORITE"
        } else if self.ci_width_1x2() > 0.20 {
            "VOLATILE"
        } else if self.confidence_1x2 == "HIGH" {
            "HIGH CONFIDENCE"
        } else if self.top_two_gap() < 0.10 {
            "EVEN MATCH"
        } else if self.under_25_prob > 0.70 && self.btts_no_prob > 0.60 {
            "LOW SCORING"
        } else if self.prob_draw > 0.35 && self.under_25_prob > 0.60 {
            "TACTICAL"
        } else {
            "STANDARD"
        }
    }

    pub fn headline(&self) -> String {
        let home = &self.home_team;
        let away = &self.away_team;
        let fav = self.favorite_label();
        let max = self.max_prob();
        let total_xg = self.dc_home_xg + self.dc_away_xg;

        if self.top_two_gap() < 0.10 && self.under_25_prob > 0.60 {
            format!("Everything points toward a tense, tactical stalemate.")
        } else if max > 0.70 {
            let fav_name = if fav == "home" { home } else { away };
            format!("{} are expected to dominate.", fav_name)
        } else if max > 0.55 && total_xg > 2.5 {
            let fav_name = if fav == "home" { home } else { away };
            format!("{} are expected to control this one comfortably.", fav_name)
        } else if self.ci_width_1x2() > 0.20 {
            format!("This one could go either way — expect the unexpected.")
        } else if self.top_two_gap() < 0.10 {
            format!("A closely fought contest where margins will decide it.")
        } else {
            let fav_name = if fav == "home" { home } else { away };
            format!("{} hold the edge but nothing is guaranteed.", fav_name)
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct FeatureView {
    pub match_id: String,
    pub match_date: String,
    pub home_team: String,
    pub away_team: String,
    pub group_name: Option<String>,
    pub home_elo: Option<f64>,
    pub away_elo: Option<f64>,
    pub home_form_score: Option<f64>,
    pub away_form_score: Option<f64>,
    pub home_win_rate_l5: Option<f64>,
    pub away_win_rate_l5: Option<f64>,
    pub home_goals_scored_l5: Option<f64>,
    pub away_goals_scored_l5: Option<f64>,
    pub home_xg_for_avg: Option<f64>,
    pub away_xg_for_avg: Option<f64>,
    pub home_xg_diff: Option<f64>,
    pub away_xg_diff: Option<f64>,
    pub h2h_matches_played: Option<i32>,
    pub h2h_home_wins: Option<i32>,
    pub h2h_draws: Option<i32>,
    pub h2h_away_wins: Option<i32>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ModelParams {
    pub id: i32,
    pub model_version: String,
    pub fitted_at: String,
    pub dc_params: Option<serde_json::Value>,
    pub calibration_corrections: Option<serde_json::Value>,
    pub feature_model_metadata: Option<serde_json::Value>,
    pub validation_metrics: Option<serde_json::Value>,
    pub n_training_matches: Option<i32>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ValidationMetrics {
    pub consensus_brier: Option<f64>,
    pub per_source_brier: Option<std::collections::HashMap<String, f64>>,
    pub biases: Option<Biases>,
    pub temporal: Option<TemporalValidation>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Biases {
    pub home: Option<f64>,
    pub draw: Option<f64>,
    pub away: Option<f64>,
    pub favorite: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TemporalValidation {
    pub brier_model: Option<f64>,
    pub brier_baseline: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FeatureModelMeta {
    pub use_feature_model: Option<bool>,
    pub negligible_signal: Option<bool>,
    pub mean_abs_correction: Option<f64>,
    pub loo_brier_with: Option<f64>,
    pub loo_brier_without: Option<f64>,
}

impl ModelParams {
    fn parse_json<T: serde::de::DeserializeOwned>(v: &serde_json::Value) -> Option<T> {
        match v {
            serde_json::Value::Object(_) | serde_json::Value::Array(_) => {
                serde_json::from_value::<T>(v.clone()).ok()
            }
            serde_json::Value::String(s) => serde_json::from_str::<T>(s).ok(),
            _ => None,
        }
    }

    pub fn validation(&self) -> Option<ValidationMetrics> {
        self.validation_metrics
            .as_ref()
            .and_then(|v| Self::parse_json::<ValidationMetrics>(v))
    }

    pub fn feature_meta(&self) -> Option<FeatureModelMeta> {
        self.feature_model_metadata
            .as_ref()
            .and_then(|v| Self::parse_json::<FeatureModelMeta>(v))
    }
}

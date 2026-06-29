use crate::models::{FeatureView, MatchPrediction, ModelParams};
use crate::splash_data::{AliveTeamRow, NextMatch, NextMatchRow};
use reqwest::Client;

pub struct SupabaseClient {
    client: Client,
    base_url: String,
    api_key: String,
}

impl SupabaseClient {
    pub fn new() -> Self {
        let base_url = std::env::var("SUPABASE_URL").unwrap_or_default();
        let api_key = std::env::var("SUPABASE_ANON_KEY")
            .or_else(|_| std::env::var("SUPABASE_KEY"))
            .unwrap_or_default();

        let mut dotenv_path = std::path::PathBuf::from(
            std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string()),
        );
        dotenv_path.push("..");
        dotenv_path.push(".env");

        let mut base_url = base_url;
        let mut api_key = api_key;

        if base_url.is_empty() || api_key.is_empty() {
            if let Ok(content) = std::fs::read_to_string(&dotenv_path) {
                for line in content.lines() {
                    let line = line.trim();
                    if let Some(val) = line.strip_prefix("SUPABASE_URL=") {
                        if base_url.is_empty() {
                            base_url = val.to_string();
                        }
                    } else if let Some(val) = line.strip_prefix("SUPABASE_ANON_KEY=") {
                        if api_key.is_empty() {
                            api_key = val.to_string();
                        }
                    } else if let Some(val) = line.strip_prefix("SUPABASE_KEY=") {
                        if api_key.is_empty() {
                            api_key = val.to_string();
                        }
                    }
                }
            }
        }

        if base_url.is_empty() || api_key.is_empty() {
            // Try current dir
            if let Ok(content) = std::fs::read_to_string(".env") {
                for line in content.lines() {
                    let line = line.trim();
                    if let Some(val) = line.strip_prefix("SUPABASE_URL=") {
                        if base_url.is_empty() {
                            base_url = val.to_string();
                        }
                    } else if let Some(val) = line.strip_prefix("SUPABASE_ANON_KEY=") {
                        if api_key.is_empty() {
                            api_key = val.to_string();
                        }
                    } else if let Some(val) = line.strip_prefix("SUPABASE_KEY=") {
                        if api_key.is_empty() {
                            api_key = val.to_string();
                        }
                    }
                }
            }
        }

        Self {
            client: Client::new(),
            base_url,
            api_key,
        }
    }

    async fn fetch_table<T: serde::de::DeserializeOwned>(
        &self,
        table: &str,
        query: &str,
    ) -> Result<Vec<T>, String> {
        let url = format!("{}/rest/v1/{}?{}", self.base_url, table, query);
        let resp = self
            .client
            .get(&url)
            .header("apikey", &self.api_key)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .send()
            .await
            .map_err(|e| format!("Request failed: {e}"))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("HTTP {status}: {body}"));
        }

        resp.json::<Vec<T>>()
            .await
            .map_err(|e| format!("JSON parse failed: {e}"))
    }

    pub async fn fetch_predictions(&self) -> Result<Vec<MatchPrediction>, String> {
        self.fetch_table(
            "match_predictions",
            "order=match_date.asc&select=*",
        )
        .await
    }

    pub async fn fetch_model_params(&self) -> Result<ModelParams, String> {
        let params: Vec<ModelParams> = self
            .fetch_table("model_params", "order=id.desc&limit=1&select=*")
            .await?;
        params
            .into_iter()
            .next()
            .ok_or_else(|| "No model params found".to_string())
    }

    pub async fn fetch_feature_view(
        &self,
        match_id: &str,
    ) -> Result<FeatureView, String> {
        let features: Vec<FeatureView> = self
            .fetch_table(
                "clean_wc_feature_view",
                &format!("match_id=eq.{match_id}&select=*"),
            )
            .await?;
        features
            .into_iter()
            .next()
            .ok_or_else(|| format!("Feature view not found for match {match_id}"))
    }

    pub async fn fetch_next_match(&self) -> Result<NextMatch, String> {
        let rows: Vec<NextMatchRow> = self
            .fetch_table("clean_wc_fixtures", crate::splash_data::next_match_query())
            .await?;
        rows.into_iter()
            .map(NextMatch::from)
            .next()
            .ok_or_else(|| "No upcoming matches found".to_string())
    }

    pub async fn fetch_alive_teams(&self) -> Result<Vec<String>, String> {
        let rows: Vec<AliveTeamRow> = self
            .fetch_table(
                "clean_wc_fixtures",
                crate::splash_data::alive_teams_query(),
            )
            .await?;

        let mut eliminated: Vec<String> = Vec::new();
        let mut all_teams: Vec<String> = Vec::new();
        for row in rows {
            let home = &row.home_team;
            let away = &row.away_team;
            if home.contains('/')
                || home.starts_with("Winner")
                || home.starts_with("Loser")
                || away.contains('/')
                || away.starts_with("Winner")
                || away.starts_with("Loser")
            {
                continue;
            }
            if let Some(ref result) = row.result_1x2 {
                match result.as_str() {
                    "H" => eliminated.push(away.clone()),
                    "A" => eliminated.push(home.clone()),
                    _ => {}
                }
            }
            for team in [home.clone(), away.clone()] {
                if !all_teams.contains(&team) {
                    all_teams.push(team);
                }
            }
        }
        let alive: Vec<String> = all_teams
            .into_iter()
            .filter(|t| !eliminated.contains(t))
            .collect();
        Ok(alive)
    }
}

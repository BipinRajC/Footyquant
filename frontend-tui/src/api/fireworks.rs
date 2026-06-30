use crate::models::MatchPrediction;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize)]
pub struct MatchPromptData {
    pub home_team: String,
    pub away_team: String,
    pub stage: String,
    pub match_date: String,
    pub prob_home: f64,
    pub prob_draw: f64,
    pub prob_away: f64,
    pub home_qualify_prob: f64,
    pub away_qualify_prob: f64,
    pub confidence: String,
    pub home_elo: String,
    pub away_elo: String,
    pub home_form: String,
    pub away_form: String,
    pub dc_home_xg: f64,
    pub dc_away_xg: f64,
    pub over_25_prob: f64,
    pub under_25_prob: f64,
    pub btts_yes_prob: f64,
    pub ah_line: f64,
    pub ah_home_prob: f64,
    pub ah_away_prob: f64,
    pub narrative: String,
}

impl MatchPromptData {
    pub fn from_prediction(pred: &MatchPrediction, home_elo: Option<f64>, away_elo: Option<f64>, home_form: Option<f64>, away_form: Option<f64>) -> Self {
        Self {
            home_team: pred.home_team.clone(),
            away_team: pred.away_team.clone(),
            stage: pred.stage.clone(),
            match_date: pred.match_date.clone(),
            prob_home: pred.prob_home,
            prob_draw: pred.prob_draw,
            prob_away: pred.prob_away,
            home_qualify_prob: pred.home_qualify_prob.unwrap_or(pred.prob_home),
            away_qualify_prob: pred.away_qualify_prob.unwrap_or(pred.prob_away),
            confidence: pred.confidence_1x2.clone(),
            home_elo: home_elo.map(|e| format!("{:.0}", e)).unwrap_or_else(|| "\u{2014}".to_string()),
            away_elo: away_elo.map(|e| format!("{:.0}", e)).unwrap_or_else(|| "\u{2014}".to_string()),
            home_form: home_form.map(|f| format!("{:.2}", f)).unwrap_or_else(|| "\u{2014}".to_string()),
            away_form: away_form.map(|f| format!("{:.2}", f)).unwrap_or_else(|| "\u{2014}".to_string()),
            dc_home_xg: pred.dc_home_xg,
            dc_away_xg: pred.dc_away_xg,
            over_25_prob: pred.over_25_prob,
            under_25_prob: pred.under_25_prob,
            btts_yes_prob: pred.btts_yes_prob,
            ah_line: pred.ah_line,
            ah_home_prob: pred.ah_home_prob,
            ah_away_prob: pred.ah_away_prob,
            narrative: pred.narrative.clone(),
        }
    }

    pub fn to_prompt_text(&self) -> String {
        format!(
            r#"Analyze the following World Cup 2026 knockout match and suggest SAFE betting opportunities.

## Match Context
- Stage: {}
- Date: {}
- {} vs {}

## Model Predictions (MATCHDAY v2.0.0)
- 1X2 (90' + stoppage): {}% / {}% / {}%
- To Qualify: {}% / {}%
- Confidence: {}
- Expected Goals (DC): {:.2} vs {:.2}
- Over 2.5: {}% | Under 2.5: {}%
- Both Teams to Score: {}%
- Asian Handicap: Line {}, {}% / {}%

## Team Stats
- Elo: {} vs {}
- Form: {} vs {}

## Model Narrative
{}

## Your Task
Provide an independent analysis focused on SAFE betting opportunities. Consider:
1. Which markets have the highest probability and lowest risk?
2. Is the <to qualify> market a safe bet given the probabilities?
3. Is <both teams to score> likely based on xG and form?
4. Is <over/under 2.5> a confident prediction?
5. Is the <1x2> market reliable for 90' + stoppage time?
6. Are there any mismatches between probabilities that create value?

Recommend only bets where the model confidence is HIGH or the probability gap is significant. Avoid suggesting risky parlays or long shots. Be specific with your recommendations and explain your reasoning."#,
            self.stage, self.match_date, self.home_team, self.away_team,
            fmt_pct(self.prob_home), fmt_pct(self.prob_draw), fmt_pct(self.prob_away),
            fmt_pct(self.home_qualify_prob), fmt_pct(self.away_qualify_prob),
            self.confidence,
            self.dc_home_xg, self.dc_away_xg,
            fmt_pct(self.over_25_prob), fmt_pct(self.under_25_prob),
            fmt_pct(self.btts_yes_prob),
            fmt_ah(self.ah_line), fmt_pct(self.ah_home_prob), fmt_pct(self.ah_away_prob),
            self.home_elo, self.away_elo,
            self.home_form, self.away_form,
            self.narrative,
        )
    }
}

fn fmt_pct(p: f64) -> String {
    format!("{}", (p * 100.0) as u32)
}

fn fmt_ah(line: f64) -> String {
    if line > 0.0 {
        format!("+{:.1}", line)
    } else {
        format!("{:.1}", line)
    }
}

#[derive(Debug, Deserialize)]
struct FireworksResponse {
    choices: Vec<FireworksChoice>,
}

#[derive(Debug, Deserialize)]
struct FireworksChoice {
    message: FireworksMessage,
}

#[derive(Debug, Deserialize)]
struct FireworksMessage {
    content: String,
}

pub async fn generate_ai_prompt(
    api_key: &str,
    data: &MatchPromptData,
) -> Result<String, String> {
    let client = reqwest::Client::new();
    let prompt_text = data.to_prompt_text();

    let body = serde_json::json!({
        "model": "accounts/fireworks/models/deepseek-v4-flash",
        "messages": [
            {
                "role": "system",
                "content": "You are a betting research assistant. Generate a concise, copy-pasteable prompt that a user can feed into any LLM for independent match analysis. Focus on SAFE betting opportunities, particularly on markets like <to qualify>, <both teams to score>, <over/under X goals>, <1x2 for 90 + stoppage time> and more if you think it is an inherently safer bet based upon all the stats provided to you. Return ONLY the prompt text, no additional commentary."
            },
            {
                "role": "user",
                "content": format!("Create a SAFE betting research prompt for this match. Focus on low-risk markets like to qualify, both teams to score, over/under goals, and 1x2. Include all relevant context, probabilities, and stats so any LLM can give an informed second opinion:\n\n{}", prompt_text)
            }
        ],
        "max_tokens": 1500,
        "temperature": 0.7
    });

    let response = client
        .post("https://api.fireworks.ai/inference/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("API request failed: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let text = response.text().await.unwrap_or_default();
        return Err(format!("API error {}: {}", status, text));
    }

    let result: FireworksResponse = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse response: {}", e))?;

    result
        .choices
        .into_iter()
        .next()
        .map(|c| c.message.content)
        .ok_or_else(|| "No response from model".to_string())
}

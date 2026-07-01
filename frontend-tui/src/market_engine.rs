use crate::models::{FeatureView, MatchPrediction};

#[derive(Debug, Clone)]
pub struct MarketRecommendation {
    pub market: &'static str,
    pub selection: String,
    pub confidence: &'static str,
    pub confidence_stars: &'static str,
    pub reason: Vec<String>,
    pub risk: &'static str,
    pub stake: u8,
}

pub fn evaluate_markets(
    pred: &MatchPrediction,
    feature: Option<&FeatureView>,
) -> Vec<MarketRecommendation> {
    let mut recs: Vec<MarketRecommendation> = Vec::new();

    let home = &pred.home_team;
    let away = &pred.away_team;
    let elo_home = feature.and_then(|f| f.home_elo).unwrap_or(1500.0);
    let elo_away = feature.and_then(|f| f.away_elo).unwrap_or(1500.0);
    let elo_diff = elo_home - elo_away;
    let form_home = feature.and_then(|f| f.home_form_score).unwrap_or(0.5);
    let form_away = feature.and_then(|f| f.away_form_score).unwrap_or(0.5);
    let xg_home = pred.dc_home_xg;
    let xg_away = pred.dc_away_xg;
    let combined_xg = xg_home + xg_away;

    // 1. Match Winner (1X2)
    let favorite = if pred.prob_home >= pred.prob_away {
        home
    } else {
        away
    };
    let fav_prob = pred.prob_home.max(pred.prob_away);
    if fav_prob >= 0.50 {
        let (stars, conf, risk, stake) = rate(fav_prob, elo_diff.abs(), 50.0);
        let mut reasons = vec![format!("{}% model probability", (fav_prob * 100.0) as u32)];
        if elo_diff.abs() > 100.0 {
            reasons.push(format!("+{:.0} Elo advantage", elo_diff.abs()));
        }
        if (xg_home - xg_away).abs() > 0.5 {
            reasons.push(format!("xG edge: {:.2} vs {:.2}", xg_home, xg_away));
        }
        recs.push(MarketRecommendation {
            market: "Match Winner",
            selection: format!("{} to Win", favorite),
            confidence: conf,
            confidence_stars: stars,
            reason: reasons,
            risk,
            stake,
        });
    }

    // 2. To Qualify
    let qual_fav = if pred.home_qualify_prob.unwrap_or(pred.prob_home)
        >= pred.away_qualify_prob.unwrap_or(pred.prob_away)
    {
        home
    } else {
        away
    };
    let qual_prob = pred
        .home_qualify_prob
        .unwrap_or(pred.prob_home)
        .max(pred.away_qualify_prob.unwrap_or(pred.prob_away));
    if qual_prob >= 0.50 {
        let (stars, conf, risk, stake) = rate(qual_prob, elo_diff.abs(), 50.0);
        let mut reasons = vec![format!(
            "{}% to qualify probability",
            (qual_prob * 100.0) as u32
        )];
        if elo_diff.abs() > 100.0 {
            reasons.push(format!("+{:.0} Elo advantage", elo_diff.abs()));
        }
        recs.push(MarketRecommendation {
            market: "To Qualify",
            selection: format!("{} to Qualify", qual_fav),
            confidence: conf,
            confidence_stars: stars,
            reason: reasons,
            risk,
            stake,
        });
    }

    // 3. Double Chance
    let dc_home = pred.prob_home + pred.prob_draw;
    let dc_away = pred.prob_away + pred.prob_draw;
    let dc_fav = if dc_home >= dc_away { home } else { away };
    let dc_prob = dc_home.max(dc_away);
    if dc_prob >= 0.65 {
        let (stars, conf, risk, stake) = rate(dc_prob, elo_diff.abs(), 30.0);
        let opponent = if dc_fav == home { away } else { home };
        recs.push(MarketRecommendation {
            market: "Double Chance",
            selection: format!("{} or Draw ({})", dc_fav, opponent),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("{}% combined probability", (dc_prob * 100.0) as u32),
                format!(
                    "Only {}% chance of {} winning outright",
                    ((1.0 - dc_prob) * 100.0) as u32,
                    opponent
                ),
            ],
            risk,
            stake,
        });
    }

    // 4. Draw No Bet
    let dnb_prob = pred.prob_home / (pred.prob_home + pred.prob_away);
    if dnb_prob >= 0.55 {
        let (stars, conf, risk, stake) = rate(dnb_prob, elo_diff.abs(), 40.0);
        recs.push(MarketRecommendation {
            market: "Draw No Bet",
            selection: format!("{} (Draw No Bet)", home),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!(
                    "{}% implied probability (excluding draw)",
                    (dnb_prob * 100.0) as u32
                ),
                format!(
                    "Draw priced at {}% — stake returned if draw",
                    (pred.prob_draw * 100.0) as u32
                ),
            ],
            risk,
            stake,
        });
    }

    // 5. Over/Under 2.5 Goals
    let ou_prob = pred.over_25_prob.max(pred.under_25_prob);
    let ou_selection = if pred.over_25_prob >= pred.under_25_prob {
        "Over 2.5"
    } else {
        "Under 2.5"
    };
    if ou_prob >= 0.55 {
        let (stars, conf, risk, stake) = rate(ou_prob, (combined_xg - 2.5).abs() * 10.0, 30.0);
        let mut reasons = vec![
            format!("{}% model probability", (ou_prob * 100.0) as u32),
            format!("Combined xG: {:.2}", combined_xg),
        ];
        if ou_prob >= 0.65 {
            reasons.push("High conviction in this market".to_string());
        }
        recs.push(MarketRecommendation {
            market: "Over/Under 2.5",
            selection: ou_selection.to_string(),
            confidence: conf,
            confidence_stars: stars,
            reason: reasons,
            risk,
            stake,
        });
    }

    // 6. Team Over/Under Goals
    if xg_home >= 1.5 {
        let (stars, conf, risk, stake) = rate(xg_home / 3.0, elo_diff.max(0.0), 30.0);
        recs.push(MarketRecommendation {
            market: "Team Over/Under",
            selection: format!("{} Over 1.5 Team Goals", home),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("Expected xG: {:.2}", xg_home),
                format!("Most likely scoreline favors {} scoring", home),
            ],
            risk,
            stake,
        });
    }
    if xg_away >= 1.5 {
        let (stars, conf, risk, stake) = rate(xg_away / 3.0, (-elo_diff).max(0.0), 30.0);
        recs.push(MarketRecommendation {
            market: "Team Over/Under",
            selection: format!("{} Over 1.5 Team Goals", away),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("Expected xG: {:.2}", xg_away),
                format!("Most likely scoreline favors {} scoring", away),
            ],
            risk,
            stake,
        });
    }

    // 7. Both Teams to Score
    let btts_prob = pred.btts_yes_prob;
    if btts_prob >= 0.50 {
        let (stars, conf, risk, stake) = rate(btts_prob, combined_xg * 5.0, 30.0);
        let selection = if btts_prob >= 0.50 { "Yes" } else { "No" };
        recs.push(MarketRecommendation {
            market: "Both Teams to Score",
            selection: format!("BTTS {}", selection),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("{}% model probability", (btts_prob * 100.0) as u32),
                format!("Combined xG: {:.2}", combined_xg),
            ],
            risk,
            stake,
        });
    }

    // 8. Asian Handicap
    if pred.ah_home_prob >= 0.55 || pred.ah_away_prob >= 0.55 {
        let ah_prob = pred.ah_home_prob.max(pred.ah_away_prob);
        let ah_side = if pred.ah_home_prob >= pred.ah_away_prob {
            home
        } else {
            away
        };
        let ah_line_str = if pred.ah_home_prob >= pred.ah_away_prob {
            format!("{:.1}", pred.ah_line)
        } else {
            format!("{:.1}", -pred.ah_line)
        };
        let (stars, conf, risk, stake) = rate(ah_prob, elo_diff.abs(), 30.0);
        recs.push(MarketRecommendation {
            market: "Asian Handicap",
            selection: format!("{} ({})", ah_side, ah_line_str),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("{}% model probability", (ah_prob * 100.0) as u32),
                format!("Line {:.1} provides insurance", pred.ah_line.abs()),
            ],
            risk,
            stake,
        });
    }

    // 9. Team to Score First
    let ts_home_prob = pred.prob_home / (pred.prob_home + pred.prob_away) * 0.7 + 0.15;
    if ts_home_prob >= 0.55 {
        let (stars, conf, risk, stake) = rate(ts_home_prob, elo_diff.max(0.0), 30.0);
        recs.push(MarketRecommendation {
            market: "Team to Score First",
            selection: format!("{} to Score First", home),
            confidence: conf,
            confidence_stars: stars,
            reason: vec![
                format!("Higher xG ({:.2} vs {:.2})", xg_home, xg_away),
                format!("Home advantage +{} Elo", (elo_diff as i32)),
            ],
            risk,
            stake,
        });
    }

    // Sort by confidence (Very High first, then High, Medium, Low)
    let order = |c: &str| -> u8 {
        match c {
            "Very High" => 0,
            "High" => 1,
            "Medium" => 2,
            "Low" => 3,
            _ => 4,
        }
    };
    recs.sort_by_key(|r| order(r.confidence));

    recs
}

fn rate(
    prob: f64,
    supporting_strength: f64,
    threshold: f64,
) -> (&'static str, &'static str, &'static str, u8) {
    let adjusted = prob + (supporting_strength / 500.0).min(0.15);
    let adjusted = adjusted.min(0.95);

    if adjusted >= 0.75 {
        ("★★★★★", "Very High", "Low", 5)
    } else if adjusted >= 0.65 {
        ("★★★★☆", "High", "Low", 4)
    } else if adjusted >= 0.58 {
        ("★★★☆☆", "High", "Medium", 3)
    } else if adjusted >= 0.52 {
        ("★★☆☆☆", "Medium", "Medium", 2)
    } else {
        ("★☆☆☆☆", "Low", "High", 1)
    }
}

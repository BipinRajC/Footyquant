use crate::models::FeatureView;
use crate::theme;
use ratatui::text::{Line, Span};

pub fn render_team_compare<'a>(
    feature: &FeatureView,
    home: &'a str,
    away: &'a str,
    bar_width: usize,
) -> Vec<Line<'a>> {
    let mut lines = Vec::new();

    let header = Line::from(vec![Span::raw(format!(
        "                    {:<14}        {:<14}",
        home, away
    ))]);
    lines.push(header);

    let comparisons: Vec<(&str, Option<f64>, Option<f64>, f64)> = vec![
        ("Elo Rating", feature.home_elo, feature.away_elo, 2200.0),
        (
            "Form Score",
            feature.home_form_score,
            feature.away_form_score,
            1.0,
        ),
        (
            "xG For Avg",
            feature.home_xg_for_avg,
            feature.away_xg_for_avg,
            2.5,
        ),
        (
            "Win Rate L5",
            feature.home_win_rate_l5,
            feature.away_win_rate_l5,
            1.0,
        ),
        (
            "Goals Scored",
            feature.home_goals_scored_l5,
            feature.away_goals_scored_l5,
            3.5,
        ),
    ];

    for (label, home_val, away_val, max_val) in comparisons {
        let hv = home_val.unwrap_or(0.0);
        let av = away_val.unwrap_or(0.0);
        let home_bar = theme::make_block_bar((hv / max_val).clamp(0.0, 1.0), bar_width);
        let away_bar = theme::make_block_bar((av / max_val).clamp(0.0, 1.0), bar_width);

        lines.push(Line::from(vec![
            Span::styled(format!(" {:<12} ", label), theme::metadata()),
            Span::styled(home_bar, theme::label_amber()),
            Span::styled(format!(" {:>5} ", format_val(hv)), theme::number()),
            Span::styled(away_bar, theme::narrative()),
            Span::styled(format!(" {:>5}", format_val(av)), theme::number()),
        ]));
    }

    lines
}

fn format_val(v: f64) -> String {
    if v >= 100.0 {
        format!("{:.0}", v)
    } else if v >= 10.0 {
        format!("{:.1}", v)
    } else {
        format!("{:.2}", v)
    }
}

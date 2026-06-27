use crate::app::App;
use crate::ascii_art;
use crate::theme;
use crate::widgets::{prob_display, scoreline_grid, team_compare};
use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let [header_area, body_area, footer_area] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Min(1),
        Constraint::Length(1),
    ])
    .areas(area);

    render_header(frame, header_area);
    render_body(frame, body_area, app);
    render_footer(frame, footer_area);
}

fn render_header(frame: &mut Frame, area: Rect) {
    let brand = format!("{} MATCHDAY", theme::BRAND_GLYPH);
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(brand, theme::brand()),
            Span::raw("                        "),
            Span::styled("MATCH ANALYSIS", theme::section_header()),
        ])),
        area,
    );
}

fn render_body(frame: &mut Frame, area: Rect, app: &App) {
    let pred = match app.current_prediction() {
        Some(p) => p,
        None => {
            frame.render_widget(
                Paragraph::new("No match selected").style(theme::metadata()),
                area,
            );
            return;
        }
    };

    let bar_width = 30;
    let mut lines: Vec<Line> = Vec::new();

    // Section 1: Broadcast Headline
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::from(Span::styled(pred.headline(), theme::brand())));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 2: The Fixture
    let group = pred.group_name.as_deref().unwrap_or("?");
    let date_str = if pred.match_date.len() >= 16 {
        format!(
            "{} · {} UTC",
            &pred.match_date[..10],
            &pred.match_date[11..16]
        )
    } else {
        pred.match_date.clone()
    };

    lines.push(Line::from(Span::styled(
        format!("          GROUP {}", group),
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        format!("          {}", theme::short_separator()),
        theme::label_gray(),
    )));
    lines.push(Line::from(Span::styled(
        format!("          {}", date_str),
        theme::metadata(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Team names centered
    let home = &pred.home_team;
    let away = &pred.away_team;
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(format!("{:<16}", home.to_uppercase()), theme::team_name()),
        Span::raw("          "),
        Span::styled(format!("{:>16}", away.to_uppercase()), theme::team_name()),
    ]));

    // Elo and form
    let elo_str = if let Some(f) = &app.current_feature {
        format!(
            "          {:<16}          {:>16}",
            format!("Elo: {}", f.home_elo.map(|e| e as i32).unwrap_or(0)),
            format!("Elo: {}", f.away_elo.map(|e| e as i32).unwrap_or(0)),
        )
    } else {
        String::new()
    };
    lines.push(Line::from(Span::styled(elo_str, theme::metadata())));

    let form_str = if let Some(f) = &app.current_feature {
        format!(
            "          {:<16}          {:>16}",
            format!("Form: {:.1}", f.home_form_score.unwrap_or(0.0)),
            format!("Form: {:.1}", f.away_form_score.unwrap_or(0.0)),
        )
    } else {
        String::new()
    };
    lines.push(Line::from(Span::styled(form_str, theme::metadata())));

    lines.push(Line::from(Span::styled(
        format!("     {}", ascii_art::vs_separator()),
        theme::label_gray(),
    )));
    lines.push(Line::from(Span::styled(
        "                    vs",
        theme::label_amber(),
    )));
    lines.push(Line::from(Span::styled(
        format!("     {}", ascii_art::vs_separator()),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 3: Match Forecast
    lines.push(Line::from(Span::styled(
        "MATCH FORECAST",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));

    // 1X2
    lines.push(Line::from(Span::styled("1X2", theme::label_amber())));
    lines.push(prob_display::render_prob_bar(
        &pred.home_team,
        pred.prob_home,
        bar_width,
    ));
    lines.push(prob_display::render_prob_bar(
        "Draw",
        pred.prob_draw,
        bar_width,
    ));
    lines.push(prob_display::render_prob_bar(
        &pred.away_team,
        pred.prob_away,
        bar_width,
    ));
    lines.push(prob_display::render_confidence_line(
        &pred.confidence_1x2,
        pred.prob_home_ci.as_deref(),
    ));
    lines.push(Line::raw(""));

    // Asian Handicap
    lines.push(Line::from(Span::styled(
        "ASIAN HANDICAP",
        theme::label_amber(),
    )));
    lines.push(Line::from(vec![
        Span::raw("     Line "),
        Span::styled(format!("{:+.1}", pred.ah_line), theme::number()),
        Span::raw("    "),
        Span::styled(&pred.home_team, theme::narrative()),
        Span::styled(
            format!(" {}%", (pred.ah_home_prob * 100.0) as u32),
            theme::number(),
        ),
        Span::raw(" · "),
        Span::styled(&pred.away_team, theme::narrative()),
        Span::styled(
            format!(" {}%", (pred.ah_away_prob * 100.0) as u32),
            theme::number(),
        ),
        Span::raw("  "),
        Span::styled(
            format!("[{}]", pred.confidence_ah),
            theme::confidence_style(&pred.confidence_ah),
        ),
    ]));
    lines.push(Line::raw(""));

    // Over/Under 2.5
    lines.push(Line::from(Span::styled(
        "OVER / UNDER 2.5",
        theme::label_amber(),
    )));
    lines.push(prob_display::render_prob_bar(
        "Over 2.5",
        pred.over_25_prob,
        bar_width,
    ));
    lines.push(prob_display::render_prob_bar(
        "Under 2.5",
        pred.under_25_prob,
        bar_width,
    ));
    lines.push(prob_display::render_confidence_line(
        &pred.confidence_ou,
        pred.over_25_ci.as_deref(),
    ));
    lines.push(Line::raw(""));

    // BTTS
    lines.push(Line::from(Span::styled(
        "BOTH TEAMS TO SCORE",
        theme::label_amber(),
    )));
    lines.push(prob_display::render_prob_bar(
        "Yes",
        pred.btts_yes_prob,
        bar_width,
    ));
    lines.push(prob_display::render_prob_bar(
        "No",
        pred.btts_no_prob,
        bar_width,
    ));
    lines.push(prob_display::render_confidence_line(
        &pred.confidence_btts,
        pred.btts_yes_ci.as_deref(),
    ));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 4: Expected Goals
    lines.push(Line::from(Span::styled(
        "EXPECTED GOALS",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(&pred.home_team, theme::team_name()),
    ]));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(format!("{:.2}", pred.dc_home_xg), theme::number()),
    ]));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(
            theme::make_bar(pred.dc_home_xg / 3.0, bar_width),
            theme::label_amber(),
        ),
    ]));
    lines.push(Line::raw(""));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(&pred.away_team, theme::team_name()),
    ]));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(format!("{:.2}", pred.dc_away_xg), theme::number()),
    ]));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(
            theme::make_bar(pred.dc_away_xg / 3.0, bar_width),
            theme::label_amber(),
        ),
    ]));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 5: Likely Scorelines
    lines.push(Line::from(Span::styled(
        "LIKELY SCORELINES",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    let scorelines = pred.scorelines();
    for sl in scoreline_grid::render_scorelines(&scorelines, bar_width) {
        lines.push(sl);
    }
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 6: Tactical Outlook
    if let Some(feature) = &app.current_feature {
        lines.push(Line::from(Span::styled(
            "TACTICAL OUTLOOK",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            theme::separator(),
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
        for l in team_compare::render_team_compare(feature, &pred.home_team, &pred.away_team, 12) {
            lines.push(l);
        }
        lines.push(Line::raw(""));
        lines.push(Line::raw(""));
    }

    // Section 7: Match Context
    lines.push(Line::from(Span::styled(
        "MATCH CONTEXT",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    let stage = &pred.stage;
    let group = pred.group_name.as_deref().unwrap_or("?");
    lines.push(Line::from(Span::styled(
        format!("{} · Group {}", stage, group),
        theme::narrative(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::from(Span::styled(
        "Qualification scenarios depend on other group results.",
        theme::metadata(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 8: Match Story
    lines.push(Line::from(Span::styled(
        "MATCH STORY",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    // Wrap narrative
    let narrative = &pred.narrative;
    let max_width = area.width.saturating_sub(4) as usize;
    let words: Vec<&str> = narrative.split_whitespace().collect();
    let mut current_line = String::new();
    for word in words {
        if current_line.is_empty() {
            current_line = word.to_string();
        } else if current_line.len() + word.len() + 1 <= max_width {
            current_line.push(' ');
            current_line.push_str(word);
        } else {
            lines.push(Line::from(Span::styled(
                current_line.clone(),
                theme::narrative(),
            )));
            current_line = word.to_string();
        }
    }
    if !current_line.is_empty() {
        lines.push(Line::from(Span::styled(current_line, theme::narrative())));
    }
    lines.push(Line::raw(""));

    // Render with scroll
    let para = Paragraph::new(lines).scroll((app.scroll as u16, 0));
    frame.render_widget(para, body_area);
}

fn render_footer(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Paragraph::new("↑↓ Scroll · Esc: Back · Q: Quit").style(theme::metadata()),
        area,
    );
}

use crate::app::App;
use crate::ascii_art;
use crate::theme;
use crate::widgets::{prob_display, scoreline_grid, team_compare};
use ratatui::layout::{Constraint, Layout, Rect};
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

    let home = &pred.home_team;
    let away = &pred.away_team;
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(format!("{:<16}", home.to_uppercase()), theme::team_name()),
        Span::raw("          "),
        Span::styled(format!("{:>16}", away.to_uppercase()), theme::team_name()),
    ]));

    if let Some(f) = &app.current_feature {
        lines.push(Line::from(Span::styled(
            format!(
                "          {:<16}          {:>16}",
                format!("Elo: {}", f.home_elo.map(|e| e as i32).unwrap_or(0)),
                format!("Elo: {}", f.away_elo.map(|e| e as i32).unwrap_or(0))
            ),
            theme::metadata(),
        )));
        lines.push(Line::from(Span::styled(
            format!(
                "          {:<16}          {:>16}",
                format!("Form: {:.1}", f.home_form_score.unwrap_or(0.0)),
                format!("Form: {:.1}", f.away_form_score.unwrap_or(0.0))
            ),
            theme::metadata(),
        )));
    }

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

    // 1X2 — using thin line gauge style (━ filled, ─ unfilled)
    lines.push(Line::from(Span::styled("1X2", theme::label_amber())));
    for (label, prob) in [
        (home.as_str(), pred.prob_home),
        ("Draw", pred.prob_draw),
        (away.as_str(), pred.prob_away),
    ] {
        lines.push(render_line_gauge(label, prob, bar_width));
    }
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
        Span::styled(home.as_str(), theme::narrative()),
        Span::styled(
            format!(" {}%", (pred.ah_home_prob * 100.0) as u32),
            theme::number(),
        ),
        Span::raw(" · "),
        Span::styled(away.as_str(), theme::narrative()),
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

    // Over/Under 2.5 — using block gauge style (▮ filled, ░ unfilled)
    lines.push(Line::from(Span::styled(
        "OVER / UNDER 2.5",
        theme::label_amber(),
    )));
    lines.push(render_block_gauge("Over 2.5", pred.over_25_prob, bar_width));
    lines.push(render_block_gauge(
        "Under 2.5",
        pred.under_25_prob,
        bar_width,
    ));
    lines.push(prob_display::render_confidence_line(
        &pred.confidence_ou,
        pred.over_25_ci.as_deref(),
    ));
    lines.push(Line::raw(""));

    // BTTS — using diamond gauge style (◆ filled, ◇ unfilled)
    lines.push(Line::from(Span::styled(
        "BOTH TEAMS TO SCORE",
        theme::label_amber(),
    )));
    lines.push(render_diamond_gauge("Yes", pred.btts_yes_prob, bar_width));
    lines.push(render_diamond_gauge("No", pred.btts_no_prob, bar_width));
    lines.push(prob_display::render_confidence_line(
        &pred.confidence_btts,
        pred.btts_yes_ci.as_deref(),
    ));
    lines.push(Line::raw(""));
    lines.push(Line::raw(""));

    // Section 4: Expected Goals — using vertical bar blocks
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
        Span::styled(home.as_str(), theme::team_name()),
        Span::raw("                          "),
        Span::styled(away.as_str(), theme::team_name()),
    ]));
    lines.push(render_xg_bars(pred.dc_home_xg, pred.dc_away_xg, bar_width));
    lines.push(Line::from(vec![
        Span::raw("     "),
        Span::styled(format!("{:.2}", pred.dc_home_xg), theme::number()),
        Span::raw("                              "),
        Span::styled(format!("{:.2}", pred.dc_away_xg), theme::number()),
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
        for l in team_compare::render_team_compare(feature, home, away, 12) {
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

    let max_width = area.width.saturating_sub(4) as usize;
    let words: Vec<&str> = pred.narrative.split_whitespace().collect();
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

    let para = Paragraph::new(lines).scroll((app.scroll as u16, 0));
    frame.render_widget(para, area);
}

fn render_line_gauge(label: &str, prob: f64, width: usize) -> Line<'static> {
    let filled = ((prob * width as f64).round() as usize).min(width);
    let mut bar = String::with_capacity(width);
    for i in 0..width {
        bar.push(if i < filled { '━' } else { '─' });
    }
    let pct = format!("{}%", (prob * 100.0) as u32);
    Line::from(vec![
        Span::styled(format!("{:>10} ", label), theme::narrative()),
        Span::styled(bar, theme::label_amber()),
        Span::raw("  "),
        Span::styled(pct, theme::number()),
    ])
}

fn render_block_gauge(label: &str, prob: f64, width: usize) -> Line<'static> {
    let filled = ((prob * width as f64).round() as usize).min(width);
    let mut bar = String::with_capacity(width);
    for i in 0..width {
        bar.push(if i < filled { '▮' } else { '▯' });
    }
    let pct = format!("{}%", (prob * 100.0) as u32);
    Line::from(vec![
        Span::styled(format!("{:>10} ", label), theme::narrative()),
        Span::styled(bar, theme::label_amber()),
        Span::raw("  "),
        Span::styled(pct, theme::number()),
    ])
}

fn render_diamond_gauge(label: &str, prob: f64, width: usize) -> Line<'static> {
    let filled = ((prob * width as f64).round() as usize).min(width);
    let mut bar = String::with_capacity(width);
    for i in 0..width {
        bar.push(if i < filled { '◆' } else { '◇' });
    }
    let pct = format!("{}%", (prob * 100.0) as u32);
    Line::from(vec![
        Span::styled(format!("{:>10} ", label), theme::narrative()),
        Span::styled(bar, theme::label_amber()),
        Span::raw("  "),
        Span::styled(pct, theme::number()),
    ])
}

fn render_xg_bars(home_xg: f64, away_xg: f64, width: usize) -> Line<'static> {
    let max_xg = 3.0;
    let home_filled = ((home_xg / max_xg * width as f64).round() as usize).min(width);
    let away_filled = ((away_xg / max_xg * width as f64).round() as usize).min(width);

    let blocks = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

    let mut home_bar = String::with_capacity(width);
    for i in 0..width {
        if i < home_filled {
            let block_idx =
                ((home_xg / max_xg * blocks.len() as f64) as usize).min(blocks.len() - 1);
            home_bar.push(blocks[block_idx]);
        } else {
            home_bar.push(' ');
        }
    }

    let mut away_bar = String::with_capacity(width);
    for i in 0..width {
        if i < away_filled {
            let block_idx =
                ((away_xg / max_xg * blocks.len() as f64) as usize).min(blocks.len() - 1);
            away_bar.push(blocks[block_idx]);
        } else {
            away_bar.push(' ');
        }
    }

    Line::from(vec![
        Span::raw("     "),
        Span::styled(home_bar, theme::label_amber()),
        Span::raw("                        "),
        Span::styled(away_bar, theme::narrative()),
    ])
}

fn render_footer(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Paragraph::new("↑↓ Scroll · Esc: Back · Q: Quit").style(theme::metadata()),
        area,
    );
}

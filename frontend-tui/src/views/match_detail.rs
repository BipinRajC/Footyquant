use crate::app::App;
use crate::theme;
use crate::timeline::stage_label_for;
use crate::widgets::{prob_display, scoreline_grid, team_compare};
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Paragraph};
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

    let home = &pred.home_team;
    let away = &pred.away_team;

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
    let stage_label = stage_label_for(&pred.match_date, &pred.stage, pred.group_name.as_deref());
    let date_str = to_ist(&pred.match_date);

    lines.push(Line::from(Span::styled(
        format!("          {}", stage_label),
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
        format!("     {}", crate::ascii_art::vs_separator()),
        theme::label_gray(),
    )));
    lines.push(Line::from(Span::styled(
        "                    vs",
        theme::label_amber(),
    )));
    lines.push(Line::from(Span::styled(
        format!("     {}", crate::ascii_art::vs_separator()),
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

    // Over/Under 2.5
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

    // BTTS
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
        Span::styled(home.as_str(), theme::team_name()),
        Span::raw("                          "),
        Span::styled(away.as_str(), theme::team_name()),
    ]));
    for l in render_xg_bars(pred.dc_home_xg, pred.dc_away_xg, bar_width) {
        lines.push(l);
    }
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
    if scorelines.is_empty() {
        lines.push(Line::from(Span::styled(
            "  No scoreline data available.",
            theme::label_gray(),
        )));
    } else {
        for sl in scoreline_grid::render_scorelines(&scorelines, bar_width) {
            lines.push(sl);
        }
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
    for l in render_match_context(&stage_label) {
        lines.push(l);
    }
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
    lines.push(Line::raw(""));

    // Section 9: AI Prompt for Second Opinion
    lines.push(Line::from(Span::styled(
        "AI PROMPT FOR SECOND OPINION",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));

    if app.ai_prompt_loading {
        let spinner = crate::ascii_art::football_spinner(app.frame_count);
        lines.push(Line::from(Span::styled(
            format!("  {}  Generating prompt via DeepSeek V4 Flash...", spinner),
            theme::metadata(),
        )));
    } else if let Some(prompt) = &app.ai_prompt {
        lines.push(Line::raw(""));
        for pl in wrap_text(prompt, max_width) {
            lines.push(Line::from(Span::styled(pl, theme::narrative())));
        }
        lines.push(Line::raw(""));
        lines.push(Line::from(Span::styled(
            "Copy this prompt and paste into any LLM for independent analysis.",
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
    } else {
        lines.push(Line::from(Span::styled(
            "  Press P to generate a research prompt for additional LLM analysis",
            theme::metadata(),
        )));
        lines.push(Line::from(Span::styled(
            "  on betting opportunities for this match.",
            theme::metadata(),
        )));
    }

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

fn render_xg_bars(home_xg: f64, away_xg: f64, width: usize) -> Vec<Line<'static>> {
    let max_xg = 3.0;
    let home_ratio = (home_xg / max_xg).clamp(0.0, 1.0);
    let away_ratio = (away_xg / max_xg).clamp(0.0, 1.0);

    let home_bar = theme::make_bar(home_ratio, width);
    let away_bar = theme::make_bar(away_ratio, width);

    vec![Line::from(vec![
        Span::raw("     "),
        Span::styled(home_bar, theme::label_amber()),
        Span::raw("          "),
        Span::styled(away_bar, theme::narrative()),
    ])]
}

fn render_match_context(stage_label: &str) -> Vec<Line<'static>> {
    let round_name = format!("{} \u{00b7} Knockout Stage", stage_label);
    let path = bracket_path(stage_label);

    vec![
        Line::from(Span::styled(round_name, theme::narrative())),
        Line::raw(""),
        Line::from(Span::styled(
            format!("Winner faces TBD in the next round."),
            theme::metadata(),
        )),
        Line::from(Span::styled(
            format!("Path to final: {}", path),
            theme::metadata(),
        )),
    ]
}

fn bracket_path(stage_label: &str) -> String {
    match stage_label {
        "R32" => "R32 \u{2192} R16 \u{2192} QF \u{2192} SF \u{2192} Final",
        "R16" => "R16 \u{2192} QF \u{2192} SF \u{2192} Final",
        "QF" => "QF \u{2192} SF \u{2192} Final",
        "SF" => "SF \u{2192} Final",
        "Final" => "Final",
        _ => "Knockout Stage",
    }
    .to_string()
}

fn to_ist(match_date: &str) -> String {
    if match_date.len() < 16 {
        return "??:??".to_string();
    }
    let date_part = &match_date[..10];
    let time_part = &match_date[11..16];
    let (h, m) = match time_part.split_once(':') {
        Some((h, m)) => (h.parse::<u32>().unwrap_or(0), m.parse::<u32>().unwrap_or(0)),
        None => return "??:??".to_string(),
    };
    let total_mins = h * 60 + m + 570;
    let days_advance = total_mins / 1440;
    let day_mins = total_mins % 1440;
    let ist_h = day_mins / 60;
    let ist_m = day_mins % 60;

    let parts: Vec<&str> = date_part.split('-').collect();
    if parts.len() == 3 {
        let y: u32 = parts[0].parse().unwrap_or(0);
        let mo: u32 = parts[1].parse().unwrap_or(0);
        let d: u32 = parts[2].parse().unwrap_or(0) + days_advance;
        let (y, mo, d) = normalize_date(y, mo, d);
        format!("{:04}-{:02}-{:02} {:02}:{:02} IST", y, mo, d, ist_h, ist_m)
    } else {
        format!("{} {:02}:{:02} IST", date_part, ist_h, ist_m)
    }
}

fn normalize_date(y: u32, mo: u32, d: u32) -> (u32, u32, u32) {
    let days_in_month = |y: u32, m: u32| -> u32 {
        match m {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 => {
                if y % 4 == 0 && (y % 100 != 0 || y % 400 == 0) {
                    29
                } else {
                    28
                }
            }
            _ => 30,
        }
    };
    let mut y = y;
    let mut mo = mo;
    let mut d = d;
    loop {
        let dim = days_in_month(y, mo);
        if d <= dim {
            break;
        }
        d -= dim;
        mo += 1;
        if mo > 12 {
            mo = 1;
            y += 1;
        }
    }
    (y, mo, d)
}

fn wrap_text(text: &str, max_width: usize) -> Vec<String> {
    let words: Vec<&str> = text.split_whitespace().collect();
    let mut lines: Vec<String> = Vec::new();
    let mut current = String::new();
    for word in words {
        if current.is_empty() {
            current = word.to_string();
        } else if current.len() + word.len() + 1 <= max_width {
            current.push(' ');
            current.push_str(word);
        } else {
            lines.push(current);
            current = word.to_string();
        }
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
}

fn render_footer(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Paragraph::new(
            "\u{2191}\u{2193} Scroll \u{00b7} Esc: Back \u{00b7} P: AI Prompt \u{00b7} Q: Quit",
        )
        .style(theme::metadata()),
        area,
    );
}

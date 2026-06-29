use crate::app::App;
use crate::theme;
use crate::timeline::{display_name, TimelineEntry};
use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Cell, Paragraph, Row, Table};
use ratatui::Frame;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let [header_area, content_area, footer_area] = Layout::vertical([
        Constraint::Length(3),
        Constraint::Min(1),
        Constraint::Length(1),
    ])
    .areas(area);

    render_header(frame, header_area, app);
    render_content(frame, content_area, app);
    render_footer(
        frame,
        footer_area,
        "\u{2191}\u{2193} Navigate \u{00b7} Enter: Match Analysis \u{00b7} M: Model Room \u{00b7} Q: Quit",
    );
}

fn render_header(frame: &mut Frame, area: Rect, app: &App) {
    let brand = format!("{} MATCHDAY", theme::BRAND_GLYPH);
    let date = if app.timeline.is_empty() {
        String::new()
    } else {
        let d = app.timeline[0].match_date();
        if d.len() >= 10 {
            d[..10].to_string()
        } else {
            d.to_string()
        }
    };

    let line = Line::from(vec![
        Span::styled(brand, theme::brand()),
        Span::raw("                              "),
        Span::styled(date, theme::metadata()),
    ]);
    frame.render_widget(Paragraph::new(line), area);
}

fn render_content(frame: &mut Frame, area: Rect, app: &App) {
    if app.loading {
        let spinner = crate::ascii_art::football_spinner(app.frame_count);
        let msg = format!("  {} Loading fixtures...", spinner);
        frame.render_widget(Paragraph::new(msg).style(theme::metadata()), area);
        return;
    }

    if let Some(ref err) = app.error {
        frame.render_widget(
            Paragraph::new(format!("  Error: {err}")).style(theme::confidence_low()),
            area,
        );
        return;
    }

    if app.timeline.is_empty() {
        frame.render_widget(
            Paragraph::new("  No fixtures available. Run model.py to generate predictions.")
                .style(theme::metadata()),
            area,
        );
        return;
    }

    let [list_area, spacer, preview_area] = Layout::vertical([
        Constraint::Min(5),
        Constraint::Length(2),
        Constraint::Length(14),
    ])
    .areas(area);

    render_fixture_list(frame, list_area, app);
    render_quick_look(frame, preview_area, app);
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

fn render_fixture_list(frame: &mut Frame, area: Rect, app: &App) {
    let completed: Vec<(usize, &TimelineEntry)> = app
        .timeline
        .iter()
        .enumerate()
        .filter(|(_, e)| e.is_completed())
        .collect();
    let upcoming: Vec<(usize, &TimelineEntry)> = app
        .timeline
        .iter()
        .enumerate()
        .filter(|(_, e)| !e.is_completed())
        .collect();

    let has_completed = !completed.is_empty();
    let has_upcoming = !upcoming.is_empty();

    if has_completed && has_upcoming {
        let total = completed.len() + upcoming.len();
        let min_h = 4u16;
        let avail = area.height.saturating_sub(min_h * 2);
        let comp_h = min_h + (avail * completed.len() as u16 / total as u16);
        let upcom_h = area.height.saturating_sub(comp_h);

        let [results_area, upcoming_area] =
            Layout::vertical([Constraint::Length(comp_h), Constraint::Length(upcom_h)]).areas(area);

        render_results_section(frame, results_area, &completed, app);
        render_upcoming_section(frame, upcoming_area, &upcoming, app);
    } else if has_completed {
        render_results_section(frame, area, &completed, app);
    } else if has_upcoming {
        render_upcoming_section(frame, area, &upcoming, app);
    }
}

fn render_results_section(
    frame: &mut Frame,
    area: Rect,
    entries: &[(usize, &TimelineEntry)],
    app: &App,
) {
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled("RESULTS", theme::section_header())));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));

    for &(i, entry) in entries {
        let selected = i == app.selected_match;
        let line = render_completed_line(entry, selected);
        lines.push(line);
    }

    let total_lines = lines.len();
    let visible_lines = area.height as usize;
    let scroll = if total_lines > visible_lines {
        app.results_scroll.min(total_lines - visible_lines)
    } else {
        0
    };

    let para = Paragraph::new(lines).scroll((scroll as u16, 0));
    frame.render_widget(para, area);
}

fn render_upcoming_section(
    frame: &mut Frame,
    area: Rect,
    entries: &[(usize, &TimelineEntry)],
    app: &App,
) {
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled(
        "UPCOMING",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));

    for &(i, entry) in entries {
        let selected = i == app.selected_match;
        let line = render_upcoming_line(entry, selected, app);
        lines.push(line);
    }

    let total_lines = lines.len();
    let visible_lines = area.height as usize;
    let scroll = if total_lines > visible_lines {
        app.upcoming_scroll.min(total_lines - visible_lines)
    } else {
        0
    };

    let para = Paragraph::new(lines).scroll((scroll as u16, 0));
    frame.render_widget(para, area);
}

fn render_completed_line(entry: &TimelineEntry, selected: bool) -> Line {
    let prefix = if selected {
        format!("  {} ", theme::SELECT_GLYPH)
    } else {
        "    ".to_string()
    };

    let stage_label = entry.stage_label();
    let home = display_name(entry.home_team());
    let away = display_name(entry.away_team());

    match entry {
        TimelineEntry::Completed {
            home_score,
            away_score,
            result_1x2,
            pred_home_qual,
            pred_away_qual,
            ..
        } => {
            let result_str = format!("{} {}-{} {}", home, home_score, away_score, away);
            let result_indicator = match result_1x2.as_str() {
                "H" => " \u{2713} H".to_string(),
                "A" => " \u{2713} A".to_string(),
                _ => " \u{2713} D".to_string(),
            };

            let mut spans = vec![Span::styled(prefix, theme::label_amber())];
            if selected {
                spans.push(Span::styled(
                    format!("{:<6}", stage_label),
                    theme::label_amber(),
                ));
                spans.push(Span::styled(
                    format!("{:<24}", result_str),
                    theme::team_name(),
                ));
                spans.push(Span::styled(result_indicator, theme::label_amber()));
            } else {
                spans.push(Span::styled(
                    format!("{:<6}", stage_label),
                    theme::label_gray(),
                ));
                spans.push(Span::styled(
                    format!("{:<24}", result_str),
                    theme::narrative(),
                ));
                spans.push(Span::styled(result_indicator, theme::label_gray()));
            }

            if let (Some(hq), Some(aq)) = (pred_home_qual, pred_away_qual) {
                let predicted_home = *hq >= *aq;
                let pred_label = if predicted_home {
                    format!("  Model: {}% H", (*hq * 100.0) as u32)
                } else {
                    format!("  Model: {}% A", (*aq * 100.0) as u32)
                };
                let actual_home = result_1x2 == "H";
                let correct = predicted_home == actual_home;

                let mark = if correct {
                    Span::styled(" \u{2713}", theme::confidence_high())
                } else {
                    Span::styled(" \u{2717}", theme::confidence_low())
                };

                let pred_style = if selected {
                    theme::label_amber()
                } else {
                    theme::label_gray()
                };
                spans.push(Span::styled(pred_label, pred_style));
                spans.push(mark);
            }

            Line::from(spans)
        }
        _ => Line::raw(""),
    }
}

fn render_upcoming_line<'a>(entry: &'a TimelineEntry, selected: bool, _app: &App) -> Line<'a> {
    let prefix = if selected {
        format!("  {} ", theme::SELECT_GLYPH)
    } else {
        "    ".to_string()
    };

    let stage_label = entry.stage_label();
    let home = display_name(entry.home_team());
    let away = display_name(entry.away_team());

    match entry {
        TimelineEntry::Upcoming(pred) => {
            let time = to_ist(&pred.match_date);
            let label = pred.character_label();
            let vs_str = format!("{} v {}", home, away);

            let mut spans = vec![Span::styled(prefix, theme::label_amber())];
            if selected {
                spans.push(Span::styled(
                    format!("{:<6}", stage_label),
                    theme::label_amber(),
                ));
                spans.push(Span::styled(format!("{:<24}", vs_str), theme::team_name()));
                spans.push(Span::styled(
                    format!("{}   {}", time, label),
                    theme::label_amber(),
                ));
            } else {
                spans.push(Span::styled(
                    format!("{:<6}", stage_label),
                    theme::label_gray(),
                ));
                spans.push(Span::styled(format!("{:<24}", vs_str), theme::narrative()));
                spans.push(Span::styled(
                    format!("{}   {}", time, label),
                    theme::label_gray(),
                ));
            }

            Line::from(spans)
        }
        _ => Line::raw(""),
    }
}

fn render_quick_look(frame: &mut Frame, area: Rect, app: &App) {
    let block = Block::default()
        .borders(Borders::TOP)
        .border_type(BorderType::Rounded)
        .border_style(theme::label_gray())
        .title(Span::styled(" QUICK LOOK ", theme::section_header()));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let entry = match app.current_timeline_entry() {
        Some(e) => e,
        None => return,
    };

    match entry {
        TimelineEntry::Completed {
            home_team,
            away_team,
            home_score,
            away_score,
            result_1x2,
            pred_home_qual,
            pred_away_qual,
            ..
        } => {
            let score = format!(
                "{} {}-{} {}",
                display_name(home_team),
                home_score,
                away_score,
                display_name(away_team)
            );

            let actual_winner = if result_1x2 == "H" {
                home_team
            } else {
                away_team
            };
            let actual_loser = if result_1x2 == "H" {
                away_team
            } else {
                home_team
            };

            let mut lines = vec![
                Line::raw(""),
                Line::from(Span::styled(
                    score,
                    Style::default()
                        .fg(theme::AMBER)
                        .add_modifier(Modifier::BOLD),
                )),
                Line::raw(""),
            ];

            if let (Some(hq), Some(aq)) = (pred_home_qual, pred_away_qual) {
                let predicted_home = *hq >= *aq;
                let predicted_winner = if predicted_home { home_team } else { away_team };
                let predicted_prob = if predicted_home { *hq } else { *aq };
                let actual_home = result_1x2 == "H";
                let correct = predicted_home == actual_home;

                lines.push(Line::from(vec![
                    Span::styled("Model predicted ", theme::metadata()),
                    Span::styled(
                        format!("{} to qualify", predicted_winner),
                        theme::team_name(),
                    ),
                    Span::styled(
                        format!(" at {}%", (predicted_prob * 100.0) as u32),
                        theme::number(),
                    ),
                ]));
                lines.push(Line::raw(""));

                if correct {
                    lines.push(Line::from(vec![
                        Span::styled(
                            "  \u{2713}  ",
                            Style::default()
                                .fg(theme::GREEN)
                                .add_modifier(Modifier::BOLD),
                        ),
                        Span::styled(
                            format!("{} qualified as predicted.", predicted_winner),
                            theme::narrative(),
                        ),
                    ]));
                } else {
                    lines.push(Line::from(vec![
                        Span::styled(
                            "  \u{2717}  ",
                            Style::default().fg(theme::RED).add_modifier(Modifier::BOLD),
                        ),
                        Span::styled(
                            format!(
                                "{} qualified instead. The model favored {} ({}%).",
                                actual_winner,
                                predicted_winner,
                                (predicted_prob * 100.0) as u32
                            ),
                            theme::narrative(),
                        ),
                    ]));
                }
                lines.push(Line::raw(""));
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("{} eliminated. ", actual_loser),
                        theme::label_gray(),
                    ),
                    Span::styled(
                        format!(
                            "Final: {} {}-{} {}.",
                            home_team, home_score, away_score, away_team
                        ),
                        theme::metadata(),
                    ),
                ]));
            } else {
                lines.push(Line::from(vec![Span::styled(
                    format!("{} qualified past {}.", actual_winner, actual_loser),
                    theme::narrative(),
                )]));
                lines.push(Line::raw(""));
                lines.push(Line::from(Span::styled(
                    "No model prediction was available for this match.",
                    theme::label_gray(),
                )));
                lines.push(Line::raw(""));
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("{} eliminated. ", actual_loser),
                        theme::label_gray(),
                    ),
                    Span::styled(
                        format!(
                            "Final: {} {}-{} {}.",
                            home_team, home_score, away_score, away_team
                        ),
                        theme::metadata(),
                    ),
                ]));
            }

            frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), inner);
        }
        TimelineEntry::Upcoming(pred) => {
            let home = display_name(&pred.home_team);
            let away = display_name(&pred.away_team);

            let header = Row::new(vec![
                Cell::from(Span::styled("Metric", theme::label_amber())),
                Cell::from(Span::styled(&home, theme::team_name())),
                Cell::from(Span::styled(&away, theme::team_name())),
            ]);

            let fmt_pct = |p: f64| format!("{}%", (p * 100.0) as u32);
            let fmt_xg = |x: f64| format!("{:.1}", x);

            let elo_home = app
                .current_feature
                .as_ref()
                .and_then(|f| f.home_elo)
                .map(|e| format!("{:.0}", e))
                .unwrap_or_else(|| "\u{2014}".to_string());
            let elo_away = app
                .current_feature
                .as_ref()
                .and_then(|f| f.away_elo)
                .map(|e| format!("{:.0}", e))
                .unwrap_or_else(|| "\u{2014}".to_string());
            let form_home = app
                .current_feature
                .as_ref()
                .and_then(|f| f.home_form_score)
                .map(|f| format!("{:.2}", f))
                .unwrap_or_else(|| "\u{2014}".to_string());
            let form_away = app
                .current_feature
                .as_ref()
                .and_then(|f| f.away_form_score)
                .map(|f| format!("{:.2}", f))
                .unwrap_or_else(|| "\u{2014}".to_string());

            let qual_home = pred.home_qualify_prob.unwrap_or(pred.prob_home);
            let qual_away = pred.away_qualify_prob.unwrap_or(pred.prob_away);

            let rows = vec![
                Row::new(vec![
                    Cell::from("Elo Rating"),
                    Cell::from(elo_home),
                    Cell::from(elo_away),
                ]),
                Row::new(vec![
                    Cell::from("Form Score"),
                    Cell::from(form_home),
                    Cell::from(form_away),
                ]),
                Row::new(vec![
                    Cell::from("To Qualify"),
                    Cell::from(fmt_pct(qual_home)),
                    Cell::from(fmt_pct(qual_away)),
                ]),
                Row::new(vec![
                    Cell::from("xG"),
                    Cell::from(fmt_xg(pred.dc_home_xg)),
                    Cell::from(fmt_xg(pred.dc_away_xg)),
                ]),
                Row::new(vec![
                    Cell::from("BTTS"),
                    Cell::from(fmt_pct(pred.btts_yes_prob)),
                    Cell::from(fmt_pct(pred.btts_yes_prob)),
                ]),
                Row::new(vec![
                    Cell::from("O/U 2.5"),
                    Cell::from(fmt_pct(pred.over_25_prob)),
                    Cell::from(fmt_pct(pred.under_25_prob)),
                ]),
                Row::new(vec![
                    Cell::from("Confidence"),
                    Cell::from(Span::styled(
                        &pred.confidence_1x2,
                        theme::confidence_style(&pred.confidence_1x2),
                    )),
                    Cell::from(""),
                ]),
            ];

            let table = Table::new(
                rows,
                [
                    Constraint::Length(14),
                    Constraint::Length(14),
                    Constraint::Length(14),
                ],
            )
            .header(header)
            .column_spacing(2);

            let [table_area, summary_area] =
                Layout::vertical([Constraint::Length(9), Constraint::Min(1)]).areas(inner);

            frame.render_widget(table, table_area);

            let summary = pred.quick_summary();
            let summary_lines = wrap_text(&summary, summary_area.width as usize);
            let mut lines = vec![Line::raw("")];
            for sl in summary_lines {
                lines.push(Line::from(Span::styled(sl, theme::narrative())));
            }

            frame.render_widget(
                Paragraph::new(lines).alignment(Alignment::Left),
                summary_area,
            );
        }
    }
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

pub fn render_footer(frame: &mut Frame, area: Rect, text: &str) {
    frame.render_widget(Paragraph::new(text).style(theme::metadata()), area);
}

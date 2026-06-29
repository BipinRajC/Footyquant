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

    let [list_area, preview_area] =
        Layout::vertical([Constraint::Min(5), Constraint::Length(14)]).areas(area);

    render_fixture_list(frame, list_area, app);
    render_quick_look(frame, preview_area, app);
}

fn render_fixture_list(frame: &mut Frame, area: Rect, app: &App) {
    let mut lines: Vec<Line> = Vec::new();

    let mut seen_completed = false;
    let mut seen_upcoming = false;

    for (i, entry) in app.timeline.iter().enumerate() {
        if entry.is_completed() && !seen_completed {
            lines.push(Line::raw(""));
            lines.push(Line::from(Span::styled("RESULTS", theme::section_header())));
            lines.push(Line::from(Span::styled(
                theme::separator(),
                theme::label_gray(),
            )));
            lines.push(Line::raw(""));
            seen_completed = true;
        } else if !entry.is_completed() && !seen_upcoming {
            lines.push(Line::raw(""));
            lines.push(Line::from(Span::styled(
                "UPCOMING",
                theme::section_header(),
            )));
            lines.push(Line::from(Span::styled(
                theme::separator(),
                theme::label_gray(),
            )));
            lines.push(Line::raw(""));
            seen_upcoming = true;
        }

        let selected = i == app.selected_match;
        let prefix = if selected {
            format!("  {} ", theme::SELECT_GLYPH)
        } else {
            "    ".to_string()
        };

        let stage_label = entry.stage_label();
        let home = display_name(entry.home_team());
        let away = display_name(entry.away_team());

        let line = match entry {
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
                    "H" => format!(" \u{2713} H"),
                    "A" => format!(" \u{2713} A"),
                    _ => format!(" \u{2713} D"),
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
            TimelineEntry::Upcoming(pred) => {
                let time = if pred.match_date.len() >= 16 {
                    &pred.match_date[11..16]
                } else {
                    "??:??"
                };
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
        };

        lines.push(line);
    }

    frame.render_widget(Paragraph::new(lines), area);
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
                let actual_home = result_1x2 == "H";
                let correct = predicted_home == actual_home;

                let pred_text = if predicted_home {
                    format!("Model: {}% {} \u{2713}", (*hq * 100.0) as u32, home_team)
                } else {
                    format!("Model: {}% {} \u{2713}", (*aq * 100.0) as u32, away_team)
                };

                let verdict = if correct {
                    Span::styled(" \u{2713} Correct", theme::confidence_high())
                } else {
                    Span::styled(" \u{2717} Incorrect", theme::confidence_low())
                };

                lines.push(Line::from(vec![
                    Span::styled("Prediction: ", theme::metadata()),
                    Span::styled(pred_text, theme::narrative()),
                    verdict,
                ]));
            } else {
                lines.push(Line::from(Span::styled(
                    "No prediction available",
                    theme::label_gray(),
                )));
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
                    Cell::from("1X2"),
                    Cell::from(fmt_pct(pred.prob_home)),
                    Cell::from(fmt_pct(pred.prob_away)),
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

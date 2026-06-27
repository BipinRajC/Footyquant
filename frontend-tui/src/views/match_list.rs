use crate::app::App;
use crate::theme;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, List, ListItem, Paragraph};
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
        "↑↓ Navigate · Enter: Match Analysis · M: Model Room · Q: Quit",
    );
}

fn render_header(frame: &mut Frame, area: Rect, app: &App) {
    let brand = format!("{} MATCHDAY", theme::BRAND_GLYPH);
    let date = if app.predictions.is_empty() {
        String::new()
    } else {
        let date_str = &app.predictions[0].match_date;
        if date_str.len() >= 10 {
            date_str[..10].to_string()
        } else {
            date_str.clone()
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

    if app.predictions.is_empty() {
        frame.render_widget(
            Paragraph::new("  No upcoming fixtures. Run model.py to generate predictions.")
                .style(theme::metadata()),
            area,
        );
        return;
    }

    let [list_area, preview_area] =
        Layout::vertical([Constraint::Min(5), Constraint::Length(10)]).areas(area);

    render_fixture_list(frame, list_area, app);
    render_quick_look(frame, preview_area, app);
}

fn render_fixture_list(frame: &mut Frame, area: Rect, app: &App) {
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::raw(""));
    lines.push(Line::from(Span::styled(
        "UPCOMING FIXTURES",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));

    let items: Vec<ListItem> = app
        .predictions
        .iter()
        .enumerate()
        .map(|(i, pred)| {
            let selected = i == app.selected_match;
            let prefix = if selected {
                format!("  {} ", theme::SELECT_GLYPH)
            } else {
                "    ".to_string()
            };

            let group = pred.group_name.as_deref().unwrap_or("?");
            let time = if pred.match_date.len() >= 16 {
                &pred.match_date[11..16]
            } else {
                "??:??"
            };
            let label = pred.character_label();

            let mut spans = vec![Span::styled(prefix, theme::label_amber())];
            if selected {
                spans.push(Span::styled(
                    format!("Group {:<6}", group),
                    theme::label_amber(),
                ));
                spans.push(Span::styled(
                    format!("{:<14} vs   {:<14}", pred.home_team, pred.away_team),
                    theme::team_name(),
                ));
                spans.push(Span::styled(
                    format!("{}   {}", time, label),
                    theme::label_amber(),
                ));
            } else {
                spans.push(Span::styled(
                    format!("Group {:<6}", group),
                    theme::label_gray(),
                ));
                spans.push(Span::styled(
                    format!("{:<14} vs   {:<14}", pred.home_team, pred.away_team),
                    theme::narrative(),
                ));
                spans.push(Span::styled(
                    format!("{}   {}", time, label),
                    theme::label_gray(),
                ));
            }

            ListItem::new(Line::from(spans))
        })
        .collect();

    let list = List::new(items);
    frame.render_widget(list, area);
}

fn render_quick_look(frame: &mut Frame, area: Rect, app: &App) {
    if let Some(pred) = app.current_prediction() {
        let block = Block::default()
            .borders(Borders::TOP)
            .border_type(BorderType::Rounded)
            .border_style(theme::label_gray())
            .title(Span::styled(" QUICK LOOK ", theme::section_header()));

        let inner = block.inner(area);
        frame.render_widget(block, area);

        let scorelines = pred.scorelines();
        let top_score = scorelines
            .first()
            .map(|s| format!("{} ({}%)", s.scoreline, (s.probability * 100.0) as u32))
            .unwrap_or_default();

        let lines = vec![
            Line::raw(""),
            Line::from(vec![
                Span::styled(&pred.home_team, theme::team_name()),
                Span::raw(" vs "),
                Span::styled(&pred.away_team, theme::team_name()),
            ]),
            Line::raw(""),
            Line::from(vec![
                Span::styled(
                    format!(
                        "Home {}% │ Draw {}% │ Away {}%",
                        (pred.prob_home * 100.0) as u32,
                        (pred.prob_draw * 100.0) as u32,
                        (pred.prob_away * 100.0) as u32
                    ),
                    theme::narrative(),
                ),
                Span::raw("  "),
                Span::styled(
                    format!("[{}]", pred.confidence_1x2),
                    theme::confidence_style(&pred.confidence_1x2),
                ),
            ]),
            Line::raw(""),
            Line::from(vec![
                Span::styled("Most likely: ", theme::metadata()),
                Span::styled(top_score, theme::number()),
            ]),
            Line::from(vec![
                Span::styled("Expected goals: ", theme::metadata()),
                Span::styled(
                    format!("{:.1} — {:.1}", pred.dc_home_xg, pred.dc_away_xg),
                    theme::number(),
                ),
            ]),
        ];

        frame.render_widget(Paragraph::new(lines), inner);
    }
}

pub fn render_footer(frame: &mut Frame, area: Rect, text: &str) {
    frame.render_widget(Paragraph::new(text).style(theme::metadata()), area);
}

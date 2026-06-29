use crate::app::App;
use crate::splash_data::format_countdown;
use crate::theme;
use chrono::Utc;
use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;
use ratatui_image::Image;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let chunks = Layout::vertical([
        Constraint::Fill(1),
        Constraint::Length(3),
        Constraint::Length(1),
        Constraint::Length(4),
        Constraint::Length(3),
        Constraint::Length(2),
        Constraint::Length(2),
        Constraint::Fill(1),
    ])
    .split(area);

    render_image_zone(frame, chunks[0], app);
    render_title_zone(frame, chunks[1], app);
    render_subtitle_zone(frame, chunks[2], app);
    render_next_match_zone(frame, chunks[3], app);
    render_flags_zone(frame, chunks[4], app);
    render_fact_zone(frame, chunks[5], app);
    render_loading_zone(frame, chunks[6], app);
}

fn render_image_zone(frame: &mut Frame, area: Rect, app: &App) {
    if let (Some(image), Some(size)) = (&app.splash_image, app.splash_image_size) {
        let image_rect = centered_rect(size.width, size.height, area);
        frame.render_widget(Image::new(image), image_rect);
    } else if !app.splash_image_loaded {
        let glow = slow_pulse(app.frame_count);
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(glow));
        let placeholder = centered_rect(40, 15, area);
        frame.render_widget(block, placeholder);
    }
}

fn render_title_zone(frame: &mut Frame, area: Rect, app: &App) {
    let glow = slow_pulse(app.frame_count);
    let line = Line::from(Span::styled(
        "MATCHDAY",
        Style::default().fg(glow).add_modifier(Modifier::BOLD),
    ));
    frame.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn render_subtitle_zone(frame: &mut Frame, area: Rect, _app: &App) {
    let line = Line::from(Span::styled(
        "FIFA World Cup 2026 \u{00b7} Prediction Terminal",
        theme::metadata(),
    ));
    frame.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn render_next_match_zone(frame: &mut Frame, area: Rect, app: &App) {
    let lines = if let Some(nm) = &app.next_match {
        let now = Utc::now();
        let countdown = format_countdown(nm.match_date, now);
        vec![
            Line::raw(""),
            Line::from(Span::styled(
                format!("{} v {}", nm.home_team, nm.away_team),
                Style::default()
                    .fg(theme::WHITE)
                    .add_modifier(Modifier::BOLD),
            )),
            Line::from(Span::styled(countdown, theme::label_amber())),
        ]
    } else if app.splash_next_match_loaded {
        vec![
            Line::raw(""),
            Line::from(Span::styled("Next match unavailable", theme::label_gray())),
            Line::raw(""),
        ]
    } else {
        vec![
            Line::raw(""),
            Line::from(Span::styled("Loading next match...", theme::label_gray())),
            Line::raw(""),
        ]
    };

    frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), area);
}

fn render_flags_zone(frame: &mut Frame, area: Rect, app: &App) {
    if app.alive_teams.is_empty() {
        return;
    }

    let chunks = Layout::vertical([Constraint::Length(1), Constraint::Length(1)]).split(area);

    let count = app.alive_teams.len();
    let heading = Line::from(Span::styled(
        format!("{} Teams Still Alive", count),
        theme::label_gray(),
    ));
    frame.render_widget(
        Paragraph::new(heading).alignment(Alignment::Center),
        chunks[0],
    );

    let viewport_width = app.splash_image_size.map(|s| s.width).unwrap_or(area.width);

    let marquee_rect = centered_rect(viewport_width, 1, chunks[1]);
    let viewport_chars = marquee_rect.width as usize;

    let units: Vec<String> = app
        .alive_teams
        .iter()
        .map(|t| format!("{}   ", t.flag))
        .collect();

    let total_units = units.len();
    if total_units == 0 {
        return;
    }

    let unit_char_count: Vec<usize> = units.iter().map(|u| u.chars().count()).collect();
    let total_chars: usize = unit_char_count.iter().sum();
    if total_chars == 0 {
        return;
    }

    let scroll_pos = (app.frame_count / 12) % total_chars;

    let mut row = String::with_capacity(viewport_chars * 4);
    let mut chars_emitted = 0usize;
    let mut unit_idx = 0usize;
    let mut char_idx = 0usize;

    let unit_chars: Vec<Vec<char>> = units.iter().map(|u| u.chars().collect()).collect();

    for _ in 0..scroll_pos {
        char_idx += 1;
        while unit_idx < total_units && char_idx >= unit_chars[unit_idx].len() {
            unit_idx += 1;
            char_idx = 0;
        }
    }
    if unit_idx >= total_units {
        unit_idx = 0;
        char_idx = 0;
    }

    while chars_emitted < viewport_chars {
        let remaining_in_unit = unit_chars[unit_idx].len() - char_idx;
        let needed = viewport_chars - chars_emitted;
        let take = remaining_in_unit.min(needed);

        for c in &unit_chars[unit_idx][char_idx..char_idx + take] {
            row.push(*c);
        }
        chars_emitted += take;
        char_idx += take;

        if char_idx >= unit_chars[unit_idx].len() {
            unit_idx = (unit_idx + 1) % total_units;
            char_idx = 0;
        }
    }

    frame.render_widget(
        Paragraph::new(Line::from(Span::styled(row, Style::default()))).alignment(Alignment::Left),
        marquee_rect,
    );
}

fn render_fact_zone(frame: &mut Frame, area: Rect, app: &App) {
    let cycle = app.frame_count % 270;
    let line = if cycle < 30 {
        Line::raw("")
    } else {
        Line::from(Span::styled(app.current_fact(), theme::label_gray()))
    };
    frame.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn render_loading_zone(frame: &mut Frame, area: Rect, app: &App) {
    let all_loaded = app.splash_all_loaded();
    let dots = pulsing_dots(app.frame_count);

    let line = if all_loaded {
        Line::from(vec![
            Span::styled(dots, Style::default().fg(theme::AMBER)),
            Span::styled("  Ready \u{2014} Press any key", theme::label_gray()),
        ])
    } else {
        Line::from(vec![
            Span::styled(dots, Style::default().fg(theme::AMBER)),
            Span::styled("  Initializing prediction engine...", theme::label_gray()),
        ])
    };

    frame.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn slow_pulse(frame_num: usize) -> Color {
    let period = 180;
    let pulse = (frame_num % period) as f32 / period as f32;
    let intensity = (pulse * std::f32::consts::TAU).sin() * 0.5 + 0.5;
    if intensity > 0.5 {
        theme::AMBER
    } else {
        Color::Indexed(130)
    }
}

fn pulsing_dots(frame_num: usize) -> String {
    let phase = (frame_num / 15) % 4;
    match phase {
        0 => "\u{00b7}  ".to_string(),
        1 => "\u{00b7}\u{00b7} ".to_string(),
        2 => "\u{00b7}\u{00b7}\u{00b7}".to_string(),
        _ => "   ".to_string(),
    }
}

fn centered_rect(width: u16, height: u16, area: Rect) -> Rect {
    let x = area.x + (area.width.saturating_sub(width)) / 2;
    let y = area.y + (area.height.saturating_sub(height)) / 2;
    Rect::new(x, y, width.min(area.width), height.min(area.height))
}

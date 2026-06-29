use crate::app::App;
use crate::splash_data::format_countdown;
use crate::theme;
use chrono::Utc;
use ratatui::layout::{Alignment, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;
use ratatui_image::Image;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    if let (Some(image), Some(size)) = (&app.splash_image, app.splash_image_size) {
        let image_rect = centered_rect(size.width, size.height, area);
        frame.render_widget(Image::new(image), image_rect);

        let text_area = text_area_below(image_rect, area);
        render_text(frame, text_area, app);
    } else {
        render_text(frame, area, app);
    }
}

fn render_text(frame: &mut Frame, area: Rect, app: &App) {
    let mut lines: Vec<Line> = Vec::new();

    let glow = slow_pulse(app.frame_count);
    lines.push(Line::raw(""));
    lines.push(Line::from(Span::styled(
        "MATCHDAY",
        Style::default().fg(glow).add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(Span::styled(
        "FIFA World Cup 2026 \u{00b7} Prediction Terminal",
        theme::metadata(),
    )));
    lines.push(Line::raw(""));

    if let Some(nm) = &app.next_match {
        let now = Utc::now();
        let countdown = format_countdown(nm.match_date, now);
        lines.push(Line::from(Span::styled(
            format!("{} v {}", nm.home_team, nm.away_team),
            Style::default()
                .fg(theme::WHITE)
                .add_modifier(Modifier::BOLD),
        )));
        lines.push(Line::from(Span::styled(countdown, theme::label_amber())));
    } else if app.splash_next_match_loaded {
        lines.push(Line::from(Span::styled(
            "Next match unavailable",
            theme::label_gray(),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            "Loading next match...",
            theme::label_gray(),
        )));
    }

    lines.push(Line::raw(""));

    if !app.alive_teams.is_empty() {
        let count = app.alive_teams.len();
        lines.push(Line::from(Span::styled(
            format!("{} Teams Still Alive", count),
            theme::label_gray(),
        )));
        lines.push(Line::from(Span::styled(
            flag_grid(&app.alive_teams, area.width),
            Style::default(),
        )));
    }

    lines.push(Line::raw(""));

    let cycle = app.frame_count % 270;
    if cycle >= 30 {
        lines.push(Line::from(Span::styled(
            app.current_fact(),
            theme::label_gray(),
        )));
    } else {
        lines.push(Line::raw(""));
    }

    lines.push(Line::raw(""));

    let all_loaded = app.splash_all_loaded();
    let dots = pulsing_dots(app.frame_count);
    if all_loaded {
        lines.push(Line::from(vec![
            Span::styled(dots, Style::default().fg(theme::AMBER)),
            Span::styled("  Ready \u{2014} Press any key", theme::label_gray()),
        ]));
    } else {
        lines.push(Line::from(vec![
            Span::styled(dots, Style::default().fg(theme::AMBER)),
            Span::styled("  Initializing prediction engine...", theme::label_gray()),
        ]));
    }

    frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), area);
}

fn flag_grid(teams: &[crate::splash_data::TeamInfo], max_width: u16) -> String {
    let flags: Vec<&str> = teams.iter().map(|t| t.flag).collect();
    let per_row = 8.min(flags.len());
    let spacing = "  ";

    let mut rows: Vec<String> = Vec::new();
    for chunk in flags.chunks(per_row) {
        let row = chunk.join(spacing);
        if row.chars().count() <= max_width as usize {
            rows.push(row);
        } else {
            let half = chunk.len() / 2;
            rows.push(chunk[..half].join(spacing));
            rows.push(chunk[half..].join(spacing));
        }
    }
    rows.join("\n")
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

fn text_area_below(image_rect: Rect, area: Rect) -> Rect {
    let start_y = (image_rect.y + image_rect.height + 1).min(area.height.saturating_sub(14));
    let height = area.height.saturating_sub(start_y);
    Rect::new(area.x, start_y, area.width, height)
}

use crate::app::App;
use crate::ascii_art;
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
        Constraint::Length(4),
        Constraint::Length(4),
        Constraint::Length(3),
        Constraint::Length(2),
        Constraint::Length(1),
    ])
    .split(area);

    render_image_zone(frame, chunks[0], app);
    render_title_zone(frame, chunks[1], app);
    render_next_match_zone(frame, chunks[2], app);
    render_teams_zone(frame, chunks[3], app);
    render_fact_zone(frame, chunks[4], app);
    render_loading_zone(frame, chunks[5], app);
}

fn render_image_zone(frame: &mut Frame, area: Rect, app: &App) {
    if let (Some(image), Some(size)) = (&app.splash_image, app.splash_image_size) {
        let image_rect = centered_rect(size.width, size.height, area);
        frame.render_widget(Image::new(image), image_rect);
    } else if !app.splash_image_loaded {
        let glow = pulse_color(app.frame_count);
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(glow));
        let placeholder = centered_rect(40, 15, area);
        frame.render_widget(block, placeholder);
    }
}

fn render_title_zone(frame: &mut Frame, area: Rect, app: &App) {
    let glow = pulse_color(app.frame_count);
    let sep1 = double_separator(area.width);
    let sep2 = double_separator(area.width);

    let lines = vec![
        Line::from(Span::styled(sep1, Style::default().fg(theme::AMBER))),
        Line::from(Span::styled(
            format!("{}  MATCHDAY  {}", theme::BRAND_GLYPH, theme::BRAND_GLYPH),
            Style::default().fg(glow).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(sep2, Style::default().fg(theme::AMBER))),
        Line::from(Span::styled(
            "FIFA World Cup 2026 \u{00b7} Prediction Simulator",
            theme::metadata(),
        )),
    ];

    frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), area);
}

fn render_next_match_zone(frame: &mut Frame, area: Rect, app: &App) {
    let sep = short_double_separator(area.width);

    let mut lines = vec![Line::from(Span::styled(
        sep,
        Style::default().fg(theme::AMBER),
    ))];

    if let Some(nm) = &app.next_match {
        lines.push(Line::from(Span::styled(
            "NEXT MATCH",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            format!("{} v {} \u{00b7} {}", nm.home_team, nm.away_team, nm.stage),
            theme::team_name(),
        )));
        let now = Utc::now();
        let secs_left = nm.match_date.signed_duration_since(now).num_seconds();
        let countdown = format_countdown(nm.match_date, now);
        let color = urgency_color(app.frame_count, secs_left);
        lines.push(Line::from(Span::styled(
            countdown,
            Style::default().fg(color).add_modifier(Modifier::BOLD),
        )));
    } else if app.splash_next_match_loaded {
        lines.push(Line::from(Span::styled(
            "NEXT MATCH",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            "Next match unavailable",
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
    } else {
        lines.push(Line::from(Span::styled(
            "NEXT MATCH",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            "Loading next match...",
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
    }

    frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), area);
}

fn render_teams_zone(frame: &mut Frame, area: Rect, app: &App) {
    let sep = short_double_separator(area.width);

    let mut lines = vec![Line::from(Span::styled(
        sep,
        Style::default().fg(theme::AMBER),
    ))];

    if app.alive_teams.is_empty() && !app.splash_teams_loaded {
        lines.push(Line::from(Span::styled(
            "Loading teams...",
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
    } else if app.alive_teams.is_empty() {
        lines.push(Line::from(Span::styled(
            "Team data unavailable",
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));
    } else {
        let count = app.alive_teams.len();
        lines.push(Line::from(Span::styled(
            format!("{} TEAMS STILL IN", count),
            theme::section_header(),
        )));
        lines.push(Line::raw(""));
    }

    let chunks = Layout::vertical([Constraint::Length(2), Constraint::Length(1)]).split(area);

    frame.render_widget(
        Paragraph::new(lines).alignment(Alignment::Center),
        chunks[0],
    );

    if !app.alive_teams.is_empty() {
        render_flag_marquee(frame, chunks[1], &app.alive_teams, app.frame_count);
    }
}

fn render_flag_marquee(
    frame: &mut Frame,
    area: Rect,
    teams: &[crate::splash_data::TeamInfo],
    frame_count: usize,
) {
    let flags: String = teams.iter().map(|t| format!("{} ", t.flag)).collect();
    let doubled = format!("{}  {}", flags, flags);
    let chars: Vec<char> = doubled.chars().collect();
    let total = chars.len();
    if total == 0 {
        return;
    }
    let offset = frame_count % total;
    let width = area.width as usize;
    let window: String = (0..width).map(|i| chars[(offset + i) % total]).collect();

    frame.render_widget(Paragraph::new(window).alignment(Alignment::Left), area);
}

fn render_fact_zone(frame: &mut Frame, area: Rect, app: &App) {
    let sep = short_double_separator(area.width);

    let mut lines = vec![Line::from(Span::styled(
        sep,
        Style::default().fg(theme::AMBER),
    ))];

    let in_blank_gap = app.frame_count % 90 < 10;
    if in_blank_gap {
        lines.push(Line::raw(""));
    } else {
        lines.push(Line::from(Span::styled(
            format!("\u{1f4a1} {}", app.current_fact()),
            theme::label_gray(),
        )));
    }

    frame.render_widget(Paragraph::new(lines).alignment(Alignment::Center), area);
}

fn render_loading_zone(frame: &mut Frame, area: Rect, app: &App) {
    let progress = app.splash_progress();
    let all_loaded = app.splash_all_loaded();

    let spinner = ascii_art::football_spinner(app.frame_count);
    let bar_width = 30;
    let prob = progress as f64 / 3.0;
    let bar = theme::make_bar(prob, bar_width);

    let bar_color = if all_loaded {
        theme::GREEN
    } else {
        theme::AMBER
    };

    let line = if all_loaded {
        Line::from(vec![
            Span::styled(format!("{} ", spinner), Style::default().fg(theme::GREEN)),
            Span::styled(bar, Style::default().fg(theme::GREEN)),
            Span::styled(" Ready \u{2014} press any key", theme::label_gray()),
        ])
    } else {
        Line::from(vec![
            Span::styled(format!("{} ", spinner), Style::default().fg(theme::AMBER)),
            Span::styled(bar, Style::default().fg(bar_color)),
            Span::styled(" Loading match data...", theme::label_gray()),
        ])
    };

    frame.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn pulse_color(frame_num: usize) -> Color {
    let pulse = (frame_num % 90) as f32 / 90.0;
    let intensity = (pulse * std::f32::consts::TAU).sin() * 0.5 + 0.5;
    if intensity > 0.66 {
        theme::AMBER
    } else if intensity > 0.33 {
        Color::Indexed(208)
    } else {
        Color::Indexed(220)
    }
}

fn urgency_color(frame_num: usize, secs_left: i64) -> Color {
    if secs_left <= 0 {
        return theme::GREEN;
    }
    if secs_left <= 600 {
        if frame_num % 2 == 0 {
            theme::AMBER
        } else {
            theme::RED
        }
    } else if secs_left <= 3600 {
        let pulse = (frame_num % 30) as f32 / 30.0;
        let intensity = (pulse * std::f32::consts::TAU).sin() * 0.5 + 0.5;
        if intensity > 0.5 {
            theme::AMBER
        } else {
            theme::RED
        }
    } else {
        theme::AMBER
    }
}

fn double_separator(width: u16) -> String {
    "\u{2550}".repeat(width as usize)
}

fn short_double_separator(width: u16) -> String {
    let pad = 8.min(width as usize / 4);
    let sep_len = width.saturating_sub((pad * 2) as u16) as usize;
    format!("{}{}", " ".repeat(pad), "\u{2550}".repeat(sep_len))
}

fn centered_rect(width: u16, height: u16, area: Rect) -> Rect {
    let x = area.x + (area.width.saturating_sub(width)) / 2;
    let y = area.y + (area.height.saturating_sub(height)) / 2;
    Rect::new(x, y, width.min(area.width), height.min(area.height))
}

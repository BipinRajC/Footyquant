use crate::app::App;
use crate::theme;
use ratatui::layout::{Alignment, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;
use ratatui_image::Image;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();
    let frame_num = app.frame_count;

    if let (Some(image), Some(size)) = (&app.splash_image, app.splash_image_size) {
        let image_rect = centered_rect(size.width, size.height, area);
        frame.render_widget(Image::new(image), image_rect);

        let text_area = text_area_below(image_rect, area);
        render_text(frame, text_area, frame_num);
    } else {
        render_fallback(frame, area, frame_num);
    }
}

fn render_text(frame: &mut Frame, area: Rect, frame_num: usize) {
    let glow_color = pulse_color(frame_num);

    let lines = vec![
        Line::raw(""),
        Line::from(Span::styled(
            "Prediction Simulator TUI",
            Style::default().fg(glow_color).add_modifier(Modifier::BOLD),
        )),
        Line::raw(""),
        Line::from(Span::styled(
            "FIFA World Cup 2026 · Matchday Modeling",
            theme::metadata(),
        )),
        Line::from(Span::styled(
            "Press any key to continue",
            theme::label_gray(),
        )),
    ];

    let para = Paragraph::new(lines).alignment(Alignment::Center);
    frame.render_widget(para, area);
}

fn render_fallback(frame: &mut Frame, area: Rect, frame_num: usize) {
    let glow_color = pulse_color(frame_num);

    let lines = vec![
        Line::from(Span::styled(
            "MATCHDAY",
            Style::default().fg(glow_color).add_modifier(Modifier::BOLD),
        )),
        Line::raw(""),
        Line::from(Span::styled(
            "FIFA World Cup 2026 · Prediction Simulator TUI",
            theme::metadata(),
        )),
        Line::raw(""),
        Line::from(Span::styled("Loading splash image...", theme::label_gray())),
    ];

    let para = Paragraph::new(lines).alignment(Alignment::Center);
    frame.render_widget(para, area);
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

fn centered_rect(width: u16, height: u16, area: Rect) -> Rect {
    let x = area.x + (area.width.saturating_sub(width)) / 2;
    let y = area.y + (area.height.saturating_sub(height)) / 2;
    Rect::new(x, y, width.min(area.width), height.min(area.height))
}

fn text_area_below(image_rect: Rect, area: Rect) -> Rect {
    let start_y = (image_rect.y + image_rect.height + 2).min(area.height.saturating_sub(6));
    let height = area.height.saturating_sub(start_y);
    Rect::new(area.x, start_y, area.width, height)
}

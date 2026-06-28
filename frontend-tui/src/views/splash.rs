use crate::app::App;
use crate::ascii_art;
use crate::theme;
use ratatui::layout::Alignment;
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();
    let frame_num = app.frame_count;

    let progress = (frame_num as f32 / 180.0).min(1.0);

    let mut lines: Vec<Line> = Vec::new();

    let blank_lines = ((1.0 - progress) * 8.0) as usize;
    for _ in 0..blank_lines {
        lines.push(Line::raw(""));
    }

    if progress > 0.1 {
        let trophy_lines: Vec<&str> = ascii_art::trophy().lines().collect();
        let trophy_progress = ((progress - 0.1) / 0.4).min(1.0);
        let visible_lines = (trophy_lines.len() as f32 * trophy_progress).ceil() as usize;
        for line in trophy_lines.iter().take(visible_lines) {
            lines.push(Line::from(Span::styled(line.to_string(), theme::brand())));
        }
    }

    if progress > 0.5 {
        let title_progress = ((progress - 0.5) / 0.3).min(1.0);
        if title_progress > 0.0 {
            lines.push(Line::raw(""));
            let title = "MATCHDAY";
            let chars: Vec<char> = title.chars().collect();
            let visible_chars = (chars.len() as f32 * title_progress).ceil() as usize;
            lines.push(Line::from(Span::styled(
                chars[..visible_chars].iter().collect::<String>(),
                theme::brand(),
            )));
        }
    }

    if progress > 0.8 {
        let sub_progress = ((progress - 0.8) / 0.2).min(1.0);
        if sub_progress > 0.0 {
            lines.push(Line::raw(""));
            let subtitle = "FIFA World Cup 2026 · Prediction Terminal";
            let chars: Vec<char> = subtitle.chars().collect();
            let visible_chars = (chars.len() as f32 * sub_progress).ceil() as usize;
            lines.push(Line::from(Span::styled(
                chars[..visible_chars].iter().collect::<String>(),
                theme::metadata(),
            )));
        }
    }

    if progress > 0.9 {
        lines.push(Line::raw(""));
        lines.push(Line::raw(""));
        lines.push(Line::from(Span::styled(
            "    \"Where every match tells a story\"",
            theme::label_amber(),
        )));
    }

    let para = Paragraph::new(lines).alignment(Alignment::Center);
    frame.render_widget(para, area);
}

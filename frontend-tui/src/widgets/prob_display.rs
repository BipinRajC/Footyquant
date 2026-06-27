use crate::theme;
use ratatui::layout::Alignment;
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;

pub fn render_prob_bar(label: &str, prob: f64, width: usize) -> Line {
    let bar = theme::make_bar(prob, width);
    let pct = format!("{:>3}%", (prob * 100.0) as u32);

    Line::from(vec![
        Span::styled(format!("{:>10} ", label), theme::narrative()),
        Span::styled(bar, theme::label_amber()),
        Span::raw("  "),
        Span::styled(pct, theme::number()),
    ])
}

pub fn render_prob_bar_with_ci(
    label: &str,
    prob: f64,
    ci: Option<&[f64]>,
    width: usize,
) -> Vec<Line> {
    let mut lines = vec![render_prob_bar(label, prob, width)];

    if let Some(ci) = ci {
        if ci.len() >= 2 {
            let lo = (ci[0] * 100.0) as u32;
            let hi = (ci[1] * 100.0) as u32;
            lines.push(Line::from(vec![
                Span::raw("             "),
                Span::styled(format!("CI: {}% - {}%", lo, hi), theme::metadata()),
            ]));
        }
    }

    lines
}

pub fn render_confidence_line(confidence: &str, ci: Option<&[f64]>) -> Line {
    let ci_text = if let Some(ci) = ci {
        if ci.len() >= 2 {
            let width = ((ci[1] - ci[0]).abs() * 100.0) as u32;
            format!(" · CI ±{}%", width / 2)
        } else {
            String::new()
        }
    } else {
        String::new()
    };

    Line::from(vec![
        Span::raw("             "),
        Span::styled(
            format!("[{}{}]", confidence, ci_text),
            theme::confidence_style(confidence),
        ),
    ])
}

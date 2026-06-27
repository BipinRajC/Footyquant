use crate::theme;
use ratatui::text::{Line, Span};

pub fn render_prob_bar(label: &str, prob: f64, width: usize) -> Line<'static> {
    let bar = theme::make_bar(prob, width);
    let pct = format!("{:>3}%", (prob * 100.0) as u32);

    Line::from(vec![
        Span::styled(format!("{:>10} ", label), theme::narrative()),
        Span::styled(bar, theme::label_amber()),
        Span::raw("  "),
        Span::styled(pct, theme::number()),
    ])
}

pub fn render_confidence_line(confidence: &str, ci: Option<&[f64]>) -> Line<'static> {
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

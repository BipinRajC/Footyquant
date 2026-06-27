use crate::theme;
use ratatui::text::{Line, Span};

pub fn render_scorelines(scorelines: &[crate::models::Scoreline], width: usize) -> Vec<Line> {
    scorelines
        .iter()
        .take(5)
        .map(|s| {
            let bar = theme::make_bar(s.probability, width);
            let pct = format!("{:>5.1}%", s.probability * 100.0);

            Line::from(vec![
                Span::styled(format!("  {:>4}  ", s.scoreline), theme::number()),
                Span::styled(bar, theme::label_amber()),
                Span::raw("  "),
                Span::styled(pct, theme::narrative()),
            ])
        })
        .collect()
}

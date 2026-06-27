use ratatui::style::{Color, Modifier, Style};

pub const AMBER: Color = Color::Indexed(214);
pub const WHITE: Color = Color::White;
pub const GRAY: Color = Color::DarkGray;
pub const GREEN: Color = Color::Indexed(34);
pub const RED: Color = Color::Indexed(196);
pub const BLACK: Color = Color::Black;

pub const BRAND_GLYPH: &str = "◉";
pub const SELECT_GLYPH: &str = "▸";

pub fn brand() -> Style {
    Style::default().fg(AMBER).add_modifier(Modifier::BOLD)
}

pub fn team_name() -> Style {
    Style::default().fg(WHITE).add_modifier(Modifier::BOLD)
}

pub fn section_header() -> Style {
    Style::default().fg(AMBER).add_modifier(Modifier::BOLD)
}

pub fn number() -> Style {
    Style::default().fg(AMBER).add_modifier(Modifier::BOLD)
}

pub fn narrative() -> Style {
    Style::default().fg(WHITE)
}

pub fn metadata() -> Style {
    Style::default().fg(GRAY)
}

pub fn label_amber() -> Style {
    Style::default().fg(AMBER)
}

pub fn label_gray() -> Style {
    Style::default().fg(GRAY)
}

pub fn confidence_high() -> Style {
    Style::default().fg(GREEN).add_modifier(Modifier::BOLD)
}

pub fn confidence_medium() -> Style {
    Style::default().fg(AMBER)
}

pub fn confidence_low() -> Style {
    Style::default().fg(GRAY)
}

pub fn confidence_style(level: &str) -> Style {
    match level {
        "HIGH" => confidence_high(),
        "MEDIUM" => confidence_medium(),
        _ => confidence_low(),
    }
}

pub fn separator() -> &str {
    "───────────────────────────────────────────────────────────"
}

pub fn short_separator() -> &str {
    "───────────────────────────"
}

pub fn bar_filled() -> char {
    '▓'
}

pub fn bar_empty() -> char {
    '░'
}

pub fn bar_block() -> char {
    '█'
}

pub fn bar_fade() -> char {
    '░'
}

pub fn make_bar(prob: f64, width: usize) -> String {
    let filled = ((prob * width as f64).round() as usize).min(width);
    let mut bar = String::with_capacity(width);
    for i in 0..width {
        if i < filled {
            bar.push(bar_filled());
        } else {
            bar.push(bar_empty());
        }
    }
    bar
}

pub fn make_block_bar(prob: f64, width: usize) -> String {
    let filled = ((prob * width as f64).round() as usize).min(width);
    let mut bar = String::with_capacity(width);
    for i in 0..width {
        if i < filled {
            bar.push(bar_block());
        } else {
            bar.push(bar_fade());
        }
    }
    bar
}

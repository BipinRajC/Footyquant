pub fn trophy() -> &'static str {
    r#"
               ╔═════════╗
               ║  ▲▲▲▲▲  ║
               ║ ╱ ╳ ╳ ╲ ║
               ║╱───────╲║
               ║│ MATCH  │║
               ║│  DAY   │║
               ║╲───────╱║
               ╚═════════╝
"#
}

pub fn trophy_small() -> &'static str {
    "◉"
}

pub fn floodlights() -> &'static str {
    "╱╳╲"
}

pub fn football_spinner(frame: usize) -> &'static str {
    let spinners = ["○", "◓", "◑", "◒", "◓"];
    spinners[frame % spinners.len()]
}

pub fn vs_separator() -> &'static str {
    "═══════════════════════════"
}

use crate::app::App;
use crate::theme;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

pub fn render(frame: &mut Frame, app: &App) {
    let area = frame.area();

    let [header_area, body_area, footer_area] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Min(1),
        Constraint::Length(1),
    ])
    .areas(area);

    render_header(frame, header_area);
    render_body(frame, body_area, app);
    render_footer(frame, footer_area);
}

fn render_header(frame: &mut Frame, area: Rect) {
    let brand = format!("{} MATCHDAY", theme::BRAND_GLYPH);
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(brand, theme::brand()),
            Span::raw("                        "),
            Span::styled("THE MODEL ROOM", theme::section_header()),
        ])),
        area,
    );
}

fn render_body(frame: &mut Frame, area: Rect, app: &App) {
    let params = match &app.model_params {
        Some(p) => p,
        None => {
            let msg = if let Some(ref err) = app.error {
                format!("  Error fetching data: {err}")
            } else {
                "  No model params available. Run model.py first.".to_string()
            };
            frame.render_widget(Paragraph::new(msg).style(theme::metadata()), area);
            return;
        }
    };

    let bar_width = 24;
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::raw(""));

    // FORECAST ACCURACY
    lines.push(Line::from(Span::styled(
        "FORECAST ACCURACY",
        theme::section_header(),
    )));
    lines.push(Line::from(Span::styled(
        theme::separator(),
        theme::label_gray(),
    )));
    lines.push(Line::raw(""));
    lines.push(Line::from(Span::styled(
        "Brier scores by source (lower = better)",
        theme::metadata(),
    )));
    lines.push(Line::raw(""));

    if let Some(validation) = params.validation() {
        if let Some(sources) = &validation.per_source_brier {
            let mut sorted: Vec<_> = sources.iter().collect();
            sorted.sort_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal));

            for (source, brier) in sorted {
                let label = source_name(source);
                let bar = theme::make_bar(1.0 - *brier, bar_width);
                lines.push(Line::from(vec![
                    Span::styled(format!(" {:<12}", label), theme::narrative()),
                    Span::styled(bar, theme::label_amber()),
                    Span::styled(format!("  {:.4}", brier), theme::number()),
                ]));
            }

            if let Some(consensus) = validation.consensus_brier {
                let bar = theme::make_bar(1.0 - consensus, bar_width);
                lines.push(Line::from(vec![
                    Span::styled(" Consensus    ", theme::brand()),
                    Span::styled(bar, theme::label_amber()),
                    Span::styled(format!("  {:.4}", consensus), theme::number()),
                ]));
            }
        }

        lines.push(Line::raw(""));
        lines.push(Line::raw(""));

        // TOURNAMENT CALIBRATION
        lines.push(Line::from(Span::styled(
            "TOURNAMENT CALIBRATION",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            theme::separator(),
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));

        if let Some(biases) = &validation.biases {
            if let Some(draw_bias) = biases.draw {
                lines.push(Line::from(vec![
                    Span::styled(" Draw bias detected:  ", theme::narrative()),
                    Span::styled(format!("{:+.1}%", draw_bias * 100.0), theme::number()),
                ]));
                lines.push(Line::from(Span::styled(
                    " The market is systematically underpricing draws.",
                    theme::metadata(),
                )));
                lines.push(Line::from(Span::styled(
                    " Correction applied to all predictions.",
                    theme::metadata(),
                )));
                lines.push(Line::raw(""));

                if let Some(fav_bias) = biases.favorite {
                    lines.push(Line::from(vec![
                        Span::styled(" Favorite bias:       ", theme::narrative()),
                        Span::styled(format!("{:+.1}%", fav_bias * 100.0), theme::number()),
                    ]));
                    lines.push(Line::from(Span::styled(
                        " Favorites winning less than implied.",
                        theme::metadata(),
                    )));
                }
            }
        }

        lines.push(Line::raw(""));
        lines.push(Line::raw(""));

        // DEPLOYMENT READINESS — using line gauge style
        lines.push(Line::from(Span::styled(
            "DEPLOYMENT READINESS",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            theme::separator(),
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));

        if let Some(temporal) = &validation.temporal {
            if let (Some(model_brier), Some(baseline_brier)) =
                (temporal.brier_model, temporal.brier_baseline)
            {
                let model_filled = ((1.0 - model_brier) * bar_width as f64).round() as usize;
                let mut model_bar = String::with_capacity(bar_width);
                for i in 0..bar_width {
                    model_bar.push(if i < model_filled { '━' } else { '─' });
                }
                lines.push(Line::from(vec![
                    Span::styled(" Model Brier    ", theme::narrative()),
                    Span::styled(model_bar, theme::label_amber()),
                    Span::styled(format!("  {:.4}", model_brier), theme::number()),
                ]));

                let base_filled = ((1.0 - baseline_brier) * bar_width as f64).round() as usize;
                let mut base_bar = String::with_capacity(bar_width);
                for i in 0..bar_width {
                    base_bar.push(if i < base_filled { '━' } else { '─' });
                }
                lines.push(Line::from(vec![
                    Span::styled(" Baseline Brier ", theme::narrative()),
                    Span::styled(base_bar, theme::label_gray()),
                    Span::styled(format!("  {:.4}", baseline_brier), theme::number()),
                ]));
                lines.push(Line::raw(""));

                if model_brier < baseline_brier {
                    lines.push(Line::from(vec![
                        Span::styled(" ✓ ", theme::confidence_high()),
                        Span::styled("Model beats raw market baseline", theme::narrative()),
                    ]));
                } else {
                    lines.push(Line::from(vec![
                        Span::styled(" ✗ ", theme::confidence_low()),
                        Span::styled("Model does not beat baseline", theme::narrative()),
                    ]));
                }
            }
        }

        lines.push(Line::raw(""));
        lines.push(Line::raw(""));

        // FEATURE SIGNAL
        lines.push(Line::from(Span::styled(
            "FEATURE SIGNAL",
            theme::section_header(),
        )));
        lines.push(Line::from(Span::styled(
            theme::separator(),
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));

        if let Some(meta) = params.feature_meta() {
            if meta.negligible_signal.unwrap_or(true) {
                lines.push(Line::from(vec![
                    Span::styled(" Status: ", theme::narrative()),
                    Span::styled("NO ADDITIONAL EDGE", theme::confidence_low()),
                ]));
                lines.push(Line::raw(""));
                lines.push(Line::from(Span::styled(
                    " Elo, form, and xG features add no marginal signal beyond",
                    theme::metadata(),
                )));
                lines.push(Line::from(Span::styled(
                    " what the market has already priced in. Predictions rely",
                    theme::metadata(),
                )));
                lines.push(Line::from(Span::styled(
                    " on calibrated market consensus + Dixon-Coles.",
                    theme::metadata(),
                )));
            } else {
                lines.push(Line::from(vec![
                    Span::styled(" Status: ", theme::narrative()),
                    Span::styled("ACTIVE", theme::confidence_high()),
                ]));
                if let Some(mean_abs) = meta.mean_abs_correction {
                    lines.push(Line::from(vec![
                        Span::styled(" Mean correction: ", theme::metadata()),
                        Span::styled(format!("{:.4}", mean_abs), theme::number()),
                    ]));
                }
            }
        }

        lines.push(Line::raw(""));
        lines.push(Line::raw(""));
        lines.push(Line::from(Span::styled(
            theme::separator(),
            theme::label_gray(),
        )));
        lines.push(Line::raw(""));

        let n_matches = params.n_training_matches.unwrap_or(0);
        let fitted = if params.fitted_at.len() >= 16 {
            &params.fitted_at[..16]
        } else {
            &params.fitted_at
        };
        lines.push(Line::from(Span::styled(
            format!(
                " {} · {} training matches · Fitted: {}",
                params.model_version, n_matches, fitted
            ),
            theme::metadata(),
        )));
    }

    let para = Paragraph::new(lines).scroll((app.scroll as u16, 0));
    frame.render_widget(para, area);
}

fn render_footer(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Paragraph::new("Esc: Back · Q: Quit").style(theme::metadata()),
        area,
    );
}

fn source_name(s: &str) -> &str {
    match s {
        "xlsx_bet365" => "Bet365",
        "xlsx_betfair" => "Betfair",
        "xlsx_avg" => "Avg Odds",
        "xlsx_max" => "Max Odds",
        "kalshi" => "Kalshi",
        "polymarket" => "Polymarket",
        _ => s,
    }
}

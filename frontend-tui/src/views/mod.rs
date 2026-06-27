pub mod splash;
pub mod match_list;
pub mod match_detail;
pub mod model_stats;

use crate::app::{App, View};
use ratatui::Frame;

pub fn render(frame: &mut Frame, app: &mut App) {
    match app.view {
        View::Splash => splash::render(frame, app),
        View::MatchList => match_list::render(frame, app),
        View::MatchDetail => match_detail::render(frame, app),
        View::ModelStats => model_stats::render(frame, app),
    }
}

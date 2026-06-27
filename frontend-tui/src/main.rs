use matchday::app::App;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut app = App::new().await?;
    app.run().await?;
    Ok(())
}

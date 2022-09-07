use std::env;
use std::time::Duration;
use lazy_static::lazy_static;
use regex::Regex;
use rand::seq::SliceRandom;

use dotenv;
use mime_guess::{self, mime};
use urlencoding::encode;
use serde::Deserialize;

use serenity::async_trait;
use serenity::model::prelude::component::{ButtonStyle};
use serenity::model::prelude::{Activity, ReactionType};
use serenity::model::prelude::interaction::{MessageFlags};
use serenity::model::application::interaction::Interaction;
use serenity::model::application::interaction::InteractionResponseType;
use serenity::utils::Colour;
use serenity::model::gateway::Ready;
use serenity::prelude::*;
use tokio::time::sleep;

extern crate reqwest;

#[derive(Deserialize)]
struct ShazamAction {
    uri: String
}

#[derive(Deserialize)]
struct ShazamMetadata {
    text: String,
    title: String
}

#[derive(Deserialize)]
struct ShazamSection {
    metadata: Option<Vec<ShazamMetadata>>
}

#[derive(Deserialize)]
struct ShazamProvider {
    #[serde(rename = "type")]
    provider_type: String,
    providername: Option<String>,
    actions: Vec<ShazamAction>
}

#[derive(Deserialize)]
struct ShazamHub {
    providers: Vec<ShazamProvider>,
    options: Vec<ShazamProvider>
}

#[derive(Deserialize)]
struct ShazamImages {
    // background: String,
    // coverart: String,
    coverarthq: String
}

#[derive(Deserialize)]
struct ShazamTrack {
    title: String,
    subtitle: String,
    url: String,
    images: ShazamImages,
    sections: Vec<ShazamSection>,
    hub: ShazamHub
}

#[derive(Deserialize)]
struct ShazamResponse {
    timestamp: Option<u64>,
    track: Option<ShazamTrack>,
}

struct ShazamProviderList {
    spotify: Option<ShazamProvider>,
    apple: Option<ShazamProvider>,
    deezer: Option<ShazamProvider>,
}

struct Handler;

lazy_static! {
    static ref TWITTER_LINK_REGEX: Regex = Regex::new(
            r"(?i)https?://((fx|px|vx)?twitter|twxtter|twittpr|twitter64)\.com/\w{1,15}/status(es)?/\d+"
        ).unwrap();
    static ref LINK_REGEX: Regex = Regex::new(
            r"(?i)https?://\S+"
        ).unwrap();
    static ref CLIENT: reqwest::Client = reqwest::Client::new();
    
    static ref RANDOM_MESSAGES: Vec<String> = vec![
        "I found it!".to_string(),
        "This might be the song you're looking for.".to_string(),
        "I hope this helps.".to_string(),
        "Hey, I love this song too.".to_string(),
        "I like your taste.".to_string(),
        "I was wondering about this song too.".to_string(),
    ];
}

async fn fetch_url(url: &str) -> ShazamResponse {
    let api_server = dotenv::var("API_SERVER").unwrap();
    let url = format!("{}{}", api_server, url);
    let data = match CLIENT.get(url).send().await {
        Ok(data) => {
            // Check if the status is successful
            if data.status().is_success() {
                data.json::<ShazamResponse>().await.unwrap()
            } else {
                return ShazamResponse {
                    timestamp: None,
                    track: None
                }
            }
        },
        Err(err) => {
            panic!("API request failed: {:?}", err);
        }
    };
    return data;
}

async fn fetch_direct(url: &str) -> ShazamResponse {
    let url = &format!("/direct?url={}", encode(url));
    return fetch_url(&url).await;
}

async fn fetch_twitter(url: &str) -> ShazamResponse {
    let id = url.split('/').last().unwrap();
    let url = &format!("/twitter/{}", id);
    return fetch_url(&url).await;
}

async fn fetch_ytdl(url: &str) -> ShazamResponse {
    let url = &format!("/ytdl?url={}", encode(url));
    return fetch_url(&url).await;
}

fn should_direct_download(url: &str) -> bool {
    // Checks the URL and sees if it looks like a video or audio file (mp3, mp4, etc.)
    let url = url.to_lowercase();
    let _guess = mime_guess::from_path(url).first();
    if _guess.is_none() {
        return false;
    }
    let guess = _guess.unwrap();
    let content_type = guess.type_();
    if content_type == mime::VIDEO || content_type == mime::AUDIO {
        return true;
    } else {
        return false;
    }
}

fn matches_twitter_link(url: &str) -> bool {
    return TWITTER_LINK_REGEX.is_match(url);
}

async fn handle_response(ctx: Context, msg: &serenity::model::channel::Message, data: ShazamResponse, interaction: Option<Interaction>) {
    let mut error_embed = serenity::builder::CreateEmbed::default();
    let track = match data.track {
        Some(track) => track,
        None => {
            // If timestamp exists, then reply with no matches, otherwise return an error
            match data.timestamp {
                Some(_) => {
                    error_embed.title("No matches found")
                        .description("We searched your media for a matching song, and couldn't find anything.")
                        .color(Colour::ORANGE);
                },
                None => {
                    error_embed.title("Failed to process media")
                        .description("We tried processing the media you requested, but an error occurred somewhere along the way. Sorry about that.")
                        .color(Colour::RED);
                }
            }
            if interaction.is_some() {
                // Send as an followup message
                if let Interaction::ApplicationCommand(command) = interaction.unwrap() {
                    command.create_followup_message(&ctx.http, |f| {
                        f.embed(|e| {
                            e.0 = error_embed.0;
                            e
                        })
                    }).await.unwrap();
                }

            } else {
                if let Err(why) = msg.channel_id.send_message(&ctx.http, |m|
                    m.embed(|e| {
                        e.0 = error_embed.0;
                        e
                    })
                        .reference_message(msg)
                ).await {
                    println!("Error sending message: {:?}", why);
                }
            }
            return;
        }
    };
    println!("Found track: {}", track.title);
    let title = track.title;
    let subtitle = track.subtitle;
    let url = track.url;
    let coverart = track.images.coverarthq;

    // Set message to a random string from RANDOM_MESSAGES
    let message = RANDOM_MESSAGES.choose(&mut rand::thread_rng()).unwrap().to_string();

    // Get the metadata from the track's section 0

    let mut embed = serenity::builder::CreateEmbed::default();
    embed.title(&title)
        .description(&subtitle)
        .url(&url)
        .color(Colour::BLUE)
        .thumbnail(&coverart)
        .footer(|f| f.text("Shazam").icon_url("https://cdn.discordapp.com/attachments/165560751363325952/1014753423045955674/84px-Shazam_icon.svg1.png"));
    
    // make new ShazamProviderList
    let mut providers = ShazamProviderList {
        spotify: None,
        apple: None,
        deezer: None,
    };
    for provider in track.hub.providers {
        println!("Found provider: {}", provider.provider_type);
        match provider.provider_type.as_str() {
            "SPOTIFY" => {
                providers.spotify = Some(provider);
            },
            "DEEZER" => {
                providers.deezer = Some(provider);
            },
            _ => {}
        }
    }
    for option in track.hub.options {
        if option.providername.is_some() {
            match option.providername.clone().unwrap().as_str() {
                "applemusic" => {
                    let url = option.actions[0].uri.clone();
                    // Occurs if the song was not found on Apple Music
                    if url.starts_with("https://music.apple.com/subscribe") {
                        continue;
                    }
                },
                _ => {}
            }
        }
    }

    let mut buttons: Vec<serenity::builder::CreateButton> = Vec::new();
    
    // Iterate through providers and add them to the embed
    if providers.spotify.is_some() {
        let provider = providers.spotify.unwrap();
        let url = provider.actions[0].uri.clone().replace("spotify:search:", "https://open.spotify.com/search/");
        let mut button = serenity::builder::CreateButton::default();
        let emoji = ReactionType::try_from("<:Spotify:1014768475593506836>").unwrap();

        button.label("Spotify")
            .style(ButtonStyle::Link)
            .url(&url)
            .emoji(emoji);
        buttons.push(button);
    }

    if providers.apple.is_some() {
        let provider = providers.apple.unwrap();
        let url = provider.actions[0].uri.clone();
        let mut button = serenity::builder::CreateButton::default();
        let emoji = ReactionType::try_from("<:Apple Music:1014769073277640765>").unwrap();

        button.label("Apple Music")
            .style(ButtonStyle::Link)
            .url(&url)
            .emoji(emoji);
        buttons.push(button);
    }

    let query = encode(&format!("{} {}", title, subtitle)).to_string();
    let url = "https://music.youtube.com/search?q=".to_string() + &query;
    let mut button = serenity::builder::CreateButton::default();
    let emoji = ReactionType::try_from("<:YouTube Music:1016942966012661762>").unwrap();

    button.label("YouTube Music")
        .style(ButtonStyle::Link)
        .url(&url)
        .emoji(emoji);
    buttons.push(button);

    if providers.deezer.is_some() {
        // Shazam's Deezer links don't work in the web client, so we need to generate our own based on track title and artist name
        let query = encode(&format!("{} {}", title, subtitle)).to_string();
        let url = format!("https://www.deezer.com/search/{}", query);
        let mut button = serenity::builder::CreateButton::default();
        let emoji = ReactionType::try_from("<:Deezer:1016912951355125812>").unwrap();

        button.label("Deezer")
            .style(ButtonStyle::Link)
            .url(&url)
            .emoji(emoji);
        buttons.push(button);
    }

    // Create Action Row
    let mut action_row = serenity::builder::CreateActionRow::default();
    // Put buttons into action row
    for button in buttons {
        action_row.add_button(button);
    }

    // Cycle through metadata and add each as a field
    for section in track.sections {
        if section.metadata.is_some() {
            let metadata = section.metadata.unwrap();
            for item in metadata {
                embed.field(item.title, item.text, true);
            }
        }
    }

    // Send as an interaction followup if this is part of an interaction
    if interaction.is_some() {
        // Send as an followup message
        if let Interaction::ApplicationCommand(command) = interaction.unwrap() {
            command.create_followup_message(&ctx.http, |f| {
                f.content(message)
                    .embed(|e| {
                        e.0 = embed.0;
                        e
                    }).components(|f| {
                        f.create_action_row(|a| {
                            a.0 = action_row.0;
                            a
                        })
                    })
            }).await.unwrap();
        }

    } else {
        if let Err(why) = msg.channel_id.send_message(&ctx.http, |m|
            m.content(message)
                .embed(|e| {
                    e.0 = embed.0;
                    e
                }).components(|f| {
                    f.create_action_row(|a| {
                        a.0 = action_row.0;
                        a
                    })
                })
                .reference_message(msg)
        ).await {
            println!("Error sending message: {:?}", why);
        }
    }



}

async fn start_typing(ctx: &Context, msg: &serenity::model::channel::Message, interaction: &Option<Interaction>) {
    if interaction.is_none() {
        if let Err(why) = msg.channel_id.broadcast_typing(&ctx.http).await {
            println!("Error setting typing state: {:?}", why);
        }
    }
}

async fn check_message(ctx: Context, msg: &serenity::model::channel::Message, interaction: Option<Interaction>) {
    if !msg.attachments.is_empty() {
        let interaction = interaction.clone();
        let ctx = ctx.clone();

        println!("Attachments: {:?}", &msg.attachments);
        // Iterate through attachments and find the first one with a content_type that contains "video"
        for attachment in &msg.attachments {
            let content_type = attachment.content_type.as_ref().unwrap();
            if content_type.contains("video") || content_type.contains("audio") {
                println!("Found media attachment: {}", attachment.url);

                start_typing(&ctx, msg, &interaction).await;
                handle_response(ctx, &msg, fetch_direct(&attachment.url).await, interaction).await;

                println!("Fetched from API!");
                return;
            }
        }
    }
    // Scan embeds for direct download media
    if !msg.embeds.is_empty() {
        let interaction = interaction.clone();
        let ctx = ctx.clone();

        println!("Embeds: {:?}", &msg.embeds);
        for embed in &msg.embeds {
            if let Some(url) = &embed.url {
                if should_direct_download(url) {
                    println!("Found media embed: {}", url);

                    start_typing(&ctx, msg, &interaction).await;
                    handle_response(ctx, &msg, fetch_direct(&url).await, interaction).await;

                    println!("Fetched from API!");
                    return;
                } else if matches_twitter_link(url) {
                    println!("Found twitter link: {}", url);

                    start_typing(&ctx, msg, &interaction).await;
                    handle_response(ctx, &msg, fetch_twitter(&url).await, interaction).await;

                    println!("Fetched from API!");
                    return;
                }
            }
        }
    }
    // Scan for links
    if !msg.content.is_empty() {

        let interaction = interaction.clone();
        let ctx = ctx.clone();
        println!("Content: {}", &msg.content);

        // Match links using LINK_REGEX
        for link in LINK_REGEX.find_iter(&msg.content) {

            let url = link.as_str();
            println!("Found link: {}", url);

            // Check if the link is a direct download link
            if should_direct_download(url) {
                println!("Found media: {}", url);

                start_typing(&ctx, msg, &interaction).await;
                handle_response(ctx, &msg, fetch_direct(&url).await, interaction).await;
                return;
            } else if matches_twitter_link(url) {
                println!("Found twitter link: {}", url);

                start_typing(&ctx, msg, &interaction).await;
                handle_response(ctx, &msg, fetch_twitter(&url).await, interaction).await;
                return;
            } else {
                println!("Let's try processing link using ytdl method: {}", url);

                start_typing(&ctx, msg, &interaction).await;
                handle_response(ctx, &msg, fetch_ytdl(&url).await, interaction).await;
                return;
            }

        }
    }
}

#[async_trait]
impl EventHandler for Handler {
    async fn message(&self, ctx: Context, msg: serenity::model::channel::Message) {
        // If message is empty and has no attachments, then return
        if msg.content.is_empty() && msg.attachments.is_empty() {
            return;
        }

        if msg.author.bot { return; } // Ignore pings from bots
        println!("CREATE_MESSAGE from {}", msg.author.name);

        check_message(ctx, &msg, None).await;
    }

    async fn ready(&self, ctx: Context, ready: Ready) {
        if let Some(shard) = ready.shard {
            // Note that array index 0 is 0-indexed, while index 1 is 1-indexed.
            //
            // This may seem unintuitive, but it models Discord's behaviour.
            println!("READY ({}) on shard {}/{}!", ready.user.name, shard[0], shard[1],);

            ctx.set_activity(Activity::listening("your music!")).await;
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        let interaction_clone = interaction.clone();
        if let Interaction::ApplicationCommand(command) = interaction {
            // println!("Received command interaction: {:#?}", command);
            let name = &command.data.name;

            if name == "help" {
                if let Err(why) = command
                    .create_interaction_response(&ctx.http, |response| {
                        response
                            .kind(InteractionResponseType::ChannelMessageWithSource)
                            .interaction_response_data(|message| {
                                message.embed(|embed| {
                                    embed.title("What's That Song?")
                                        .description("**Figure out what song is playing with videos, audio files, and web URLs on Discord.**

There are a few ways you can use the bot:

:one: If you have access to use application commands in a server, you will be able to match other people's media and URLs by right clicking their message and choosing **Apps > What's That Song?**. The results will be sent to you privately.

:two: Send a message in a server **@ mentioning the bot** with a URL or media file.

:three: **DM the bot** with a URL or media file.")
                                        .color(Colour::BLUE)
                                }).flags(MessageFlags::EPHEMERAL)
                            })
                    })
                    .await
                {
                    println!("Cannot respond to application command: {}", why);
                }
            } else {
                // let's send a deferred ephemeral response so we can process the music
                if let Err(why) = command
                    .create_interaction_response(&ctx.http, |response| {
                        response.kind(InteractionResponseType::DeferredChannelMessageWithSource)
                            .interaction_response_data(|message| {
                                message.flags(MessageFlags::EPHEMERAL)
                            })
                    }).await
                {
                    println!("Cannot respond to application command: {}", why);
                }
                // Get message data
                let messages = command.data.resolved.messages;
                let target_id = command.data.target_id.unwrap();
                // Get message from target_id
                let message_id = target_id.to_message_id();
                let message = messages.get(&message_id).unwrap();

                check_message(ctx, message, Some(interaction_clone)).await;
            }
        }
    }
}

#[tokio::main]
async fn main() {

    dotenv::dotenv().expect("Failed to load .env file!");
    let token = env::var("DISCORD_TOKEN").expect("Expected a token in the environment");

    let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES;
    let mut client =
        Client::builder(&token, intents).event_handler(Handler).await.expect("Err creating client");

    let manager = client.shard_manager.clone();

    tokio::spawn(async move {
        loop {
            sleep(Duration::from_secs(30)).await;

            let lock = manager.lock().await;
            let shard_runners = lock.runners.lock().await;

            for (id, runner) in shard_runners.iter() {
                println!(
                    "Shard ID {} is {} with a latency of {:?}",
                    id, runner.stage, runner.latency,
                );
            }
        }
    });

    if let Err(why) = client.start_shards(1).await {
        println!("Client error: {:?}", why);
    }
}
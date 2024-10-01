import os
import logging
import requests
from datetime import datetime, timedelta
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# File paths for song and activity lists
SONG_FILE = 'song_list.txt'
ACTIVITY_FILE = 'activity_list.txt'

# Define conversation states
SONG_NAME, SONG_ARTIST, SUGGEST_ACTIVITY = range(3)

# Define the wedding date
WEDDING_DATE = datetime(2026, 12, 12)

# Counter for tracking messages
MESSAGE_COUNTER = 0

class WeddingBot:
    def __init__(self):
        # Load the bot token from environment variables
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("Missing environment variable: TELEGRAM_BOT_TOKEN")
        
        # Initialize the Telegram bot application
        self.application = Application.builder().token(self.token).build()

        # Add command handlers
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('countdown', self.countdown))  
        self.application.add_handler(CommandHandler('faq', self.faq))  
        self.application.add_handler(CommandHandler('quote', self.quote))  # Quote command
        self.application.add_handler(CommandHandler('displaylists', self.display_lists))  # Display both lists

        # Convo handler for /song
        song_handler = ConversationHandler(
            entry_points=[CommandHandler('song', self.song_command)],
            states={
                SONG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_song_name)],
                SONG_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_song_artist)],
            },
            fallbacks=[]
        )
        self.application.add_handler(song_handler)

        # Convo handler for /suggestactivity
        activity_handler = ConversationHandler(
            entry_points=[CommandHandler('suggestactivity', self.suggest_activity)],
            states={
                SUGGEST_ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_activity)]
            },
            fallbacks=[]
        )
        self.application.add_handler(activity_handler)

        # Add a message handler to track and post a quote every 20 messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.track_messages))

        # JobQueue for automatic countdown posting
        job_queue = self.application.job_queue
        job_queue.run_repeating(self.auto_post_countdown, interval=timedelta(days=1), first=datetime.now())

        # Add error handler
        self.application.add_error_handler(self.error_handler)

    # Display both song and activity lists
    async def display_lists(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display both the song and activity lists separated by '-----'."""
        # Read song list
        song_list = "No songs available."
        if os.path.exists(SONG_FILE):
            with open(SONG_FILE, 'r') as file:
                song_list = file.read().strip() or "No songs available."

        # Read activity list
        activity_list = "No activities available."
        if os.path.exists(ACTIVITY_FILE):
            with open(ACTIVITY_FILE, 'r') as file:
                activity_list = file.read().strip() or "No activities available."

        # Combine lists with a separator
        combined_list = f"Song List:\n{song_list}\n\n-----\n\nActivity List:\n{activity_list}"

        # Send the combined list to the user
        await context.bot.send_message(chat_id=update.effective_chat.id, text=combined_list)

    # Start command
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Hello! Welcome to the Wedding Planning Bot."
        )

    # Fetch quote from ZenQuotes API
    def get_quote(self):
        try:
            response = requests.get('https://zenquotes.io/api/random')
            if response.status_code == 200:
                quote_json = response.json()
                return f"{quote_json[0]['q']} — {quote_json[0]['a']}"
            else:
                return "Sorry, I couldn't fetch a quote at the moment."
        except Exception as e:
            logger.error(f"Error fetching quote from ZenQuotes: {e}")
            return "Sorry, something went wrong while fetching the quote."

    # /quote command
    async def quote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a random quote fetched from ZenQuotes API."""
        quote = self.get_quote()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=quote)

    # Track messages and post a quote every 20 messages
    async def track_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track the number of messages in the chat, and post a quote every 20 messages."""
        global MESSAGE_COUNTER
        MESSAGE_COUNTER += 1

        if MESSAGE_COUNTER >= 20:
            MESSAGE_COUNTER = 0
            quote = self.get_quote()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Here's a motivational quote for you:\n\n{quote}")

    # Song suggestion command
    async def song_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the song adding process by asking for the song title."""
        user = update.message.from_user
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{user.first_name}, please enter the song title:"
        )
        return SONG_NAME  # Transition to SONG_NAME state

    # Get song name and ask for artist
    async def get_song_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive the song name and ask for the artist's name."""
        context.user_data['song_name'] = update.message.text
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Now, enter the artist's name:")
        return SONG_ARTIST  # Transition to SONG_ARTIST state

    # Get artist name and save the song to file
    async def get_song_artist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive the artist name, save the song, and show the updated song list."""
        song_name = context.user_data.get('song_name')
        artist_name = update.message.text

        # Save the song to file
        with open(SONG_FILE, 'a') as file:
            file.write(f"{song_name} - {artist_name}\n")

        # Notify the user and send the updated song list
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Song added! Here is the updated playlist:")

        with open(SONG_FILE, 'r') as file:
            song_list = file.read()

        await context.bot.send_message(chat_id=update.effective_chat.id, text=song_list)
        return ConversationHandler.END  # End the conversation

    # Suggest activity command
    async def suggest_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt the user to suggest an activity."""
        user = update.message.from_user
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{user.first_name}, please suggest an activity for the wedding:")
        return SUGGEST_ACTIVITY  # Transition to SUGGEST_ACTIVITY state

    # Get activity and save it to file
    async def get_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get the suggested activity from the user, save it to file, and display the updated activity list."""
        activity = update.message.text

        # Save the activity to file
        with open(ACTIVITY_FILE, 'a') as file:
            file.write(f"{activity}\n")

        # Notify the user that the activity has been added
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Activity added! Here is the updated activity list:")

        # Output the full activity list
        with open(ACTIVITY_FILE, 'r') as file:
            activity_list = file.read()

        # Send the updated activity list to the user
        await context.bot.send_message(chat_id=update.effective_chat.id, text=activity_list)
        return ConversationHandler.END  # End the conversation

    # Countdown command
    async def countdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the countdown to the wedding date."""
        days_remaining, countdown_message = self.calculate_days_until()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=countdown_message)

    # FAQ command
    async def faq(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the FAQ to the user."""
        faq_message = r"""
_About the Wedding_

*What is the date and time of the wedding?*
\- December 12th, 2026 at 2 pm\.

*Where is the wedding ceremony being held?*
\- The Club at Bella Collina\.

*Where will the reception take place?*
\- Same place, The Club at Bella Collina\.

*What is the dress code for the wedding?*
\- Semi\-Formal\/Cocktail Attire\.

*Are children invited to the wedding?*
\- If needed\.

*Is there parking available at the venue?*
\- Yes\. Carpool drivers will also be available\.

*Can I bring a plus\-one to the wedding?*
\- Request a plus\-one by the RSVP date\.

*Will there be any special dietary options at the reception?*
\- Please request\.

*Can we take photos or videos during the ceremony?*
\- Yes, and please submit them to the group chat\!

*Is there a rehearsal dinner?*
\- Not an official one, but there will be a dinner with family and close friends\.

_About the Bot_

*How do I suggest a song for the wedding playlist?*
\- Type `/song` in the chat and follow the prompts to suggest a song title and artist\. The bot will add it to the playlist\.

*How do I suggest an activity for the wedding?*
\- Type `/suggestactivity` in the chat, and the bot will prompt you to suggest a fun activity\. Once submitted, the bot will show the updated list of activities\.

*How do I check how many days are left until the wedding?*
\- Type `/daysuntil` to see the current countdown to the big day\.

*Does the bot do anything automatically?*
\- The bot automatically posts countdown updates every month\. As the wedding day approaches, it will post weekly\. In the final week, it posts daily reminders\. It also sends a motivational quote every 20 messages in the chat\. Type `/quote` to see a quote on demand\.

*What do I do if the bot isn’t responding correctly?*
\- If the bot seems unresponsive, try typing the command again or asking an admin for help\.

\-\-\-

Don't see your question? Just ask in the chat and an admin member will answer shortly\.
"""
        await context.bot.send_message(chat_id=update.effective_chat.id, text=faq_message, parse_mode='MarkdownV2')

    # Calculate the days remaining until the wedding
    def calculate_days_until(self):
        """Calculates the days, hours, and minutes until the wedding."""
        today = datetime.now()
        delta = WEDDING_DATE - today
        days_remaining = delta.days
        seconds_remaining = delta.seconds
        hours_remaining = seconds_remaining // 3600
        minutes_remaining = (seconds_remaining % 3600) // 60
        countdown_message = f"The wedding is in {days_remaining} days, {hours_remaining} hours, and {minutes_remaining} minutes!"
        return days_remaining, countdown_message
    
    # Automatically post countdown based on time left
    async def auto_post_countdown(self, context: ContextTypes.DEFAULT_TYPE):
        """Automatically post countdown updates according to the schedule."""
        days_remaining, countdown_message = self.calculate_days_until()
        chat_id = -4530637343  # Replace with your chat ID

        # Automatic posting logic
        if days_remaining > 30:
            # Post monthly
            if datetime.now().day == 1:  # Post on the 1st of the month
                await context.bot.send_message(chat_id=chat_id, text=countdown_message)

        elif days_remaining > 7:
            # Post weekly
            if datetime.now().weekday() == 0:  # Post every Monday
                await context.bot.send_message(chat_id=chat_id, text=countdown_message)

        else:
            # Post daily for the last week
            await context.bot.send_message(chat_id=chat_id, text=countdown_message)

    # Error handler
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log errors caused by updates."""
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred!")

    # Run the bot
    def run(self):
        """Start the bot."""
        self.application.run_polling()

# Main execution
if __name__ == "__main__":
    bot = WeddingBot()
    bot.run()

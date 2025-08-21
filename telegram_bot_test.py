import requests
import json
import time
from datetime import datetime

class TelegramBotTester:
    def __init__(self, base_url="https://vr-mask-booking.preview.emergentagent.com"):
        self.base_url = base_url
        self.webhook_url = f"{base_url}/api/webhook"
        self.user_id = 123456789
        self.chat_id = 123456789
        
    def send_webhook_update(self, update_data):
        """Send a webhook update to the bot"""
        try:
            response = requests.post(self.webhook_url, json=update_data)
            print(f"Webhook response: {response.status_code} - {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending webhook: {e}")
            return False
    
    def create_message_update(self, text, message_id=None):
        """Create a message update"""
        if message_id is None:
            message_id = int(time.time())
            
        return {
            "update_id": message_id,
            "message": {
                "message_id": message_id,
                "from": {
                    "id": self.user_id,
                    "is_bot": False,
                    "first_name": "Test User",
                    "username": "testuser",
                    "language_code": "ru"
                },
                "chat": {
                    "id": self.chat_id,
                    "first_name": "Test User",
                    "username": "testuser",
                    "type": "private"
                },
                "date": int(time.time()),
                "text": text
            }
        }
    
    def create_callback_update(self, callback_data, message_id=None):
        """Create a callback query update"""
        if message_id is None:
            message_id = int(time.time())
            
        return {
            "update_id": message_id,
            "callback_query": {
                "id": str(message_id),
                "from": {
                    "id": self.user_id,
                    "is_bot": False,
                    "first_name": "Test User",
                    "username": "testuser",
                    "language_code": "ru"
                },
                "message": {
                    "message_id": message_id - 1,
                    "from": {
                        "id": 8362583071,
                        "is_bot": True,
                        "first_name": "VR Rental Bot",
                        "username": "vr_rental_bot"
                    },
                    "chat": {
                        "id": self.chat_id,
                        "first_name": "Test User",
                        "username": "testuser",
                        "type": "private"
                    },
                    "date": int(time.time()) - 1,
                    "text": "Test message"
                },
                "data": callback_data
            }
        }
    
    def test_start_command(self):
        """Test /start command"""
        print("\n🤖 Testing /start command...")
        update = self.create_message_update("/start")
        success = self.send_webhook_update(update)
        if success:
            print("✅ /start command processed successfully")
        else:
            print("❌ /start command failed")
        return success
    
    def test_booking_flow(self):
        """Test the complete booking flow"""
        print("\n📝 Testing booking flow...")
        
        steps = [
            ("start_booking", "Start booking button"),
            ("masks_1", "Select 1 mask"),
            ("days_2", "Select 2 days"),
            ("date_2024-08-25", "Select date"),
        ]
        
        success_count = 0
        for callback_data, description in steps:
            print(f"   Testing: {description}")
            update = self.create_callback_update(callback_data)
            if self.send_webhook_update(update):
                success_count += 1
                time.sleep(0.5)  # Small delay between steps
            else:
                print(f"   ❌ Failed at step: {description}")
                break
        
        # Test address input
        print("   Testing: Address input")
        address_update = self.create_message_update("Test Address 123, Moscow")
        if self.send_webhook_update(address_update):
            success_count += 1
        
        print(f"📊 Booking flow: {success_count}/{len(steps)+1} steps successful")
        return success_count == len(steps) + 1
    
    def test_admin_commands(self):
        """Test admin commands"""
        print("\n👑 Testing admin commands...")
        
        # Create admin user update
        admin_update = {
            "update_id": int(time.time()),
            "message": {
                "message_id": int(time.time()),
                "from": {
                    "id": 987654321,  # Different user ID for admin
                    "is_bot": False,
                    "first_name": "Admin",
                    "username": "andrisxxx",  # Admin username
                    "language_code": "ru"
                },
                "chat": {
                    "id": 987654321,
                    "first_name": "Admin",
                    "username": "andrisxxx",
                    "type": "private"
                },
                "date": int(time.time()),
                "text": "/admin"
            }
        }
        
        success = self.send_webhook_update(admin_update)
        if success:
            print("✅ /admin command processed successfully")
            
            # Test admin callback queries
            admin_callbacks = [
                ("admin_all_bookings", "View all bookings"),
                ("admin_active_bookings", "View active bookings"),
                ("admin_stats", "View statistics")
            ]
            
            for callback_data, description in admin_callbacks:
                print(f"   Testing: {description}")
                callback_update = self.create_callback_update(callback_data)
                callback_update["callback_query"]["from"]["username"] = "andrisxxx"
                self.send_webhook_update(callback_update)
                time.sleep(0.3)
        else:
            print("❌ /admin command failed")
        
        return success
    
    def check_bookings_created(self):
        """Check if any bookings were created during testing"""
        print("\n📋 Checking if bookings were created...")
        try:
            response = requests.get(f"{self.base_url}/api/bookings")
            if response.status_code == 200:
                bookings = response.json()
                print(f"📊 Found {len(bookings)} bookings in database")
                
                if bookings:
                    latest_booking = bookings[0]
                    print(f"   Latest booking: {latest_booking.get('first_name', 'Unknown')} - {latest_booking.get('price', 0)}₽")
                    return True
                else:
                    print("   No bookings found")
                    return False
            else:
                print(f"❌ Failed to fetch bookings: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error checking bookings: {e}")
            return False

def main():
    print("🚀 Starting Telegram Bot Functionality Tests...")
    print("=" * 60)
    
    tester = TelegramBotTester()
    
    # Test basic commands
    start_success = tester.test_start_command()
    
    # Test booking flow
    booking_success = tester.test_booking_flow()
    
    # Test admin commands
    admin_success = tester.test_admin_commands()
    
    # Check if bookings were created
    bookings_created = tester.check_bookings_created()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Telegram Bot Test Results:")
    print(f"   ✅ /start command: {'PASS' if start_success else 'FAIL'}")
    print(f"   ✅ Booking flow: {'PASS' if booking_success else 'FAIL'}")
    print(f"   ✅ Admin commands: {'PASS' if admin_success else 'FAIL'}")
    print(f"   ✅ Bookings created: {'YES' if bookings_created else 'NO'}")
    
    total_tests = 4
    passed_tests = sum([start_success, booking_success, admin_success, bookings_created])
    
    print(f"\n🎯 Overall Success Rate: {passed_tests}/{total_tests} ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests >= 3:
        print("🎉 Telegram bot is functioning well!")
        return 0
    else:
        print("⚠️ Telegram bot has some issues that need attention")
        return 1

if __name__ == "__main__":
    exit(main())
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

async function run() {
  await mongoose.connect(process.env.MONGO_URI);
  const hashedPassword = await bcrypt.hash('REDACTED', 10);
  await mongoose.connection.collection('users').updateOne(
    { email: 'REDACTED_EMAIL' },
    { 
      $set: { 
        password: hashedPassword, 
        role: 'admin',
        twoFactorEnabled: false // Disables broken 2FA lock temporarily so you can log in
      } 
    },
    { upsert: true }
  );
  console.log('Admin password updated and 2FA reset successfully');
  process.exit(0);
}
run().catch(console.error);

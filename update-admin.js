const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

async function run() {
  await mongoose.connect(process.env.MONGO_URI);
  const adminEmail = process.env.ADMIN_EMAIL || 'REDACTED_EMAIL';
  const newPassword = process.env.ADMIN_PASSWORD;
  if (!newPassword) {
    console.error('ERROR: ADMIN_PASSWORD is required');
    process.exit(1);
  }
  const hashedPassword = await bcrypt.hash(newPassword, 10);
  await mongoose.connection.collection('users').updateOne(
    { email: adminEmail },
    {
      $set: {
        password_hash: hashedPassword,
        role: 'admin',
        age_verified: true,
        twofa_enabled: false
      }
    },
    { upsert: true }
  );
  console.log(`Admin password updated and 2FA reset successfully for ${adminEmail}`);
  process.exit(0);
}
run().catch(console.error);

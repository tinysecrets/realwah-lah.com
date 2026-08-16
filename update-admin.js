const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

async function run() {
  await mongoose.connect(process.env.MONGO_URI);
  const hashedPassword = await bcrypt.hash('your_new_secure_password', 10);
  await mongoose.connection.collection('users').updateOne(
    { email: 'REDACTED_EMAIL' },
    { $set: { password: hashedPassword, role: 'admin' } },
    { upsert: true }
  );
  console.log('Admin updated successfully');
  process.exit(0);
}
run().catch(console.error);

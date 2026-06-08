import { Link } from 'react-router-dom';
import { Shield, Terminal, Activity } from 'lucide-react';

/**
 * MASTER CONTROL HUB
 * 
 * Hidden admin page that lists all platform control panels
 * Only accessible to admin users
 */
const MasterControlHub = () => {
  const platforms = [
    { id: 'fire-kirin', name: 'Fire Kirin', icon: '🔥', color: '#ff4500' },
    { id: 'juwa', name: 'Juwa', icon: '🎰', color: '#00bfff' },
    { id: 'juwa2', name: 'Juwa 2', icon: '🎲', color: '#1e90ff' },
    { id: 'orion-stars', name: 'Orion Stars', icon: '⭐', color: '#9370db' },
    { id: 'ultra-panda', name: 'Ultra Panda', icon: '🐼', color: '#ff1493' },
    { id: 'panda-master', name: 'Panda Master', icon: '🎋', color: '#32cd32' },
    { id: 'game-vault', name: 'Game Vault', icon: '🏆', color: '#ffd700' }
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 border-b border-purple-500/30 py-12">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-center gap-4 mb-4">
            <Shield className="w-12 h-12 text-purple-400" />
            <div>
              <h1 className="text-5xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                Master Control Center
              </h1>
              <p className="text-gray-400 mt-2">Playwright Automation Command Center</p>
            </div>
          </div>
        </div>
      </div>

      {/* Platform Grid */}
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {platforms.map((platform) => (
            <Link
              key={platform.id}
              to={`/master-control/${platform.id}`}
              className="group bg-gray-900 border border-gray-800 hover:border-purple-500/50 rounded-xl p-8 transition-all hover:scale-105 hover:shadow-2xl hover:shadow-purple-500/20"
            >
              <div className="flex items-center justify-between mb-6">
                <div className="text-6xl">{platform.icon}</div>
                <Terminal className="w-6 h-6 text-gray-600 group-hover:text-purple-400 transition" />
              </div>
              
              <h3 className="text-2xl font-bold mb-2" style={{ color: platform.color }}>
                {platform.name}
              </h3>
              
              <p className="text-gray-400 text-sm mb-4">
                Bot Control Panel
              </p>
              
              <div className="flex items-center gap-2 text-sm text-gray-500 group-hover:text-purple-400 transition">
                <Activity className="w-4 h-4" />
                <span>View Status & Inject Credits</span>
              </div>
            </Link>
          ))}
        </div>

        {/* System Info */}
        <div className="mt-12 bg-gray-900 border border-gray-800 rounded-xl p-8">
          <h3 className="text-2xl font-bold mb-6 flex items-center gap-3">
            <Shield className="w-6 h-6 text-purple-400" />
            System Information
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
            <div>
              <h4 className="text-gray-400 font-medium mb-3">Access Level</h4>
              <p className="text-white">👑 Administrator (Full Control)</p>
            </div>
            
            <div>
              <h4 className="text-gray-400 font-medium mb-3">Capabilities</h4>
              <ul className="space-y-1 text-gray-300">
                <li>✅ View real-time bot status</li>
                <li>✅ Manual credit injection</li>
                <li>✅ Bot restart controls</li>
                <li>✅ Activity log monitoring</li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-gray-400 font-medium mb-3">Security Notice</h4>
              <p className="text-yellow-400">
                ⚠️ These routes are protected. Only accessible to admin accounts.
              </p>
            </div>
            
            <div>
              <h4 className="text-gray-400 font-medium mb-3">Audit Trail</h4>
              <p className="text-gray-300">
                All manual injections are logged in the database for compliance.
              </p>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-6 flex gap-4">
          <Link
            to="/dashboard"
            className="px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg transition"
          >
            ← Back to Dashboard
          </Link>
          
          <Link
            to="/admin"
            className="px-6 py-3 bg-purple-600 hover:bg-purple-500 rounded-lg transition"
          >
            Admin Panel →
          </Link>
        </div>
      </div>
    </div>
  );
};

export default MasterControlHub;

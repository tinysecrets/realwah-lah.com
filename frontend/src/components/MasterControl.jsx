import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Activity, 
  Zap, 
  DollarSign, 
  Users, 
  TrendingUp, 
  AlertCircle, 
  CheckCircle,
  XCircle,
  RefreshCw,
  Send,
  Terminal,
  Cpu,
  Database,
  Clock
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * MASTER CONTROL PANEL
 * 
 * Admin-only interface for monitoring and controlling Playwright automation
 * across all game platforms (Fire Kirin, Juwa, Orion Stars, etc.)
 */
const MasterControl = () => {
  const { platformId } = useParams();
  const navigate = useNavigate();
  
  const [platformStatus, setPlatformStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [injecting, setInjecting] = useState(false);
  const [logs, setLogs] = useState([]);
  
  // Manual injection form
  const [manualForm, setManualForm] = useState({
    userId: '',
    playerId: '',
    gameId: '',
    credits: '',
    reason: ''
  });

  // Platform configurations
  const PLATFORMS = {
    'fire-kirin': {
      name: 'Fire Kirin',
      color: '#ff4500',
      icon: '🔥',
      adminUrl: 'https://agent.firekirin.xyz'
    },
    'juwa': {
      name: 'Juwa',
      color: '#00bfff',
      icon: '🎰',
      adminUrl: 'https://juwa.com/agent'
    },
    'juwa2': {
      name: 'Juwa 2',
      color: '#1e90ff',
      icon: '🎲',
      adminUrl: 'https://juwa2.com/agent'
    },
    'orion-stars': {
      name: 'Orion Stars',
      color: '#9370db',
      icon: '⭐',
      adminUrl: 'https://agent.orionstars.vip'
    },
    'ultra-panda': {
      name: 'Ultra Panda',
      color: '#ff1493',
      icon: '🐼',
      adminUrl: 'https://ultrapanda.com/agent'
    },
    'panda-master': {
      name: 'Panda Master',
      color: '#32cd32',
      icon: '🎋',
      adminUrl: 'https://agent.pandamaster.vip'
    },
    'game-vault': {
      name: 'Game Vault',
      color: '#ffd700',
      icon: '🏆',
      adminUrl: 'https://agent.gamevault.com'
    }
  };

  const platform = PLATFORMS[platformId];

  const fetchPlatformStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/middleware/status`);
      
      const status = data.bridges?.[platformId] || {
        is_authenticated: false,
        session_active: false,
        last_heartbeat: null,
        has_session_cookie: false,
        has_csrf_token: false
      };
      
      setPlatformStatus(status);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, [platformId]);

  useEffect(() => {
    if (!platform) {
      navigate('/404');
      return;
    }
    
    fetchPlatformStatus();
    
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchPlatformStatus, 10000);
    return () => clearInterval(interval);
  }, [platformId, platform, navigate, fetchPlatformStatus]);

  const handleManualInject = async (e) => {
    e.preventDefault();
    
    if (!manualForm.userId || !manualForm.playerId || !manualForm.credits) {
      toast.error('Please fill in all required fields');
      return;
    }

    setInjecting(true);

    try {
      // This would call the Playwright middleware to inject credits
      const { data } = await axios.post(`${API}/admin/middleware/inject`, {
        platform_id: platformId,
        user_id: manualForm.userId,
        player_id: manualForm.playerId,
        game_id: manualForm.gameId || platformId,
        credits: parseInt(manualForm.credits),
        reason: manualForm.reason || 'Manual admin injection'
      });

      toast.success(`✅ Injected ${manualForm.credits} credits to ${manualForm.playerId}`);
      
      // Add to local logs
      setLogs(prev => [{
        timestamp: new Date().toISOString(),
        action: 'MANUAL_INJECT',
        playerId: manualForm.playerId,
        credits: manualForm.credits,
        status: 'success'
      }, ...prev].slice(0, 50));
      
      // Reset form
      setManualForm({
        userId: '',
        playerId: '',
        gameId: '',
        credits: '',
        reason: ''
      });
      
      fetchPlatformStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Injection failed');
      
      setLogs(prev => [{
        timestamp: new Date().toISOString(),
        action: 'MANUAL_INJECT',
        playerId: manualForm.playerId,
        credits: manualForm.credits,
        status: 'failed',
        error: error.response?.data?.detail
      }, ...prev].slice(0, 50));
    } finally {
      setInjecting(false);
    }
  };

  const restartBot = async () => {
    try {
      await axios.post(`${API}/admin/middleware/restart/${platformId}`);
      toast.success('Bot restart initiated');
      setTimeout(fetchPlatformStatus, 2000);
    } catch (error) {
      toast.error('Failed to restart bot');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-white text-xl">Loading Master Control...</div>
      </div>
    );
  }

  if (!platform) {
    return null;
  }

  const isOnline = platformStatus?.is_authenticated && platformStatus?.session_active;

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="text-5xl">{platform.icon}</div>
            <div>
              <h1 className="text-4xl font-bold" style={{ color: platform.color }}>
                {platform.name} Master Control
              </h1>
              <p className="text-gray-400 mt-1">Playwright Automation Dashboard</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <button
              onClick={fetchPlatformStatus}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg flex items-center gap-2 transition"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
            
            <button
              onClick={restartBot}
              className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg flex items-center gap-2 transition"
            >
              <Cpu className="w-4 h-4" />
              Restart Bot
            </button>
            
            <a
              href={platform.adminUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg flex items-center gap-2 transition"
            >
              <Terminal className="w-4 h-4" />
              Open Agent Panel
            </a>
          </div>
        </div>
      </div>

      {/* Status Cards */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <StatusCard
          icon={<Activity className="w-6 h-6" />}
          label="Bot Status"
          value={isOnline ? "ONLINE" : "OFFLINE"}
          color={isOnline ? "green" : "red"}
        />
        
        <StatusCard
          icon={<Zap className="w-6 h-6" />}
          label="Session"
          value={platformStatus?.has_session_cookie ? "ACTIVE" : "INACTIVE"}
          color={platformStatus?.has_session_cookie ? "green" : "yellow"}
        />
        
        <StatusCard
          icon={<Clock className="w-6 h-6" />}
          label="Last Heartbeat"
          value={platformStatus?.last_heartbeat 
            ? new Date(platformStatus.last_heartbeat).toLocaleTimeString() 
            : "Never"}
          color="blue"
        />
        
        <StatusCard
          icon={<Database className="w-6 h-6" />}
          label="Auth Status"
          value={platformStatus?.is_authenticated ? "AUTHENTICATED" : "NOT AUTHENTICATED"}
          color={platformStatus?.is_authenticated ? "green" : "red"}
        />
      </div>

      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Manual Injection Form */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Send className="w-6 h-6 text-purple-400" />
            <h2 className="text-2xl font-bold">Manual Credit Injection</h2>
          </div>
          
          <form onSubmit={handleManualInject} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                User ID (Database)
              </label>
              <input
                type="text"
                value={manualForm.userId}
                onChange={(e) => setManualForm({...manualForm, userId: e.target.value})}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none"
                placeholder="MongoDB User ID"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Player ID (Game Account)
              </label>
              <input
                type="text"
                value={manualForm.playerId}
                onChange={(e) => setManualForm({...manualForm, playerId: e.target.value})}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none"
                placeholder="Player username in game"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Credits to Inject
              </label>
              <input
                type="number"
                value={manualForm.credits}
                onChange={(e) => setManualForm({...manualForm, credits: e.target.value})}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none"
                placeholder="Amount"
                min="1"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Reason (Optional)
              </label>
              <input
                type="text"
                value={manualForm.reason}
                onChange={(e) => setManualForm({...manualForm, reason: e.target.value})}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-purple-500 outline-none"
                placeholder="Manual injection, promo, etc."
              />
            </div>

            <button
              type="submit"
              disabled={injecting || !isOnline}
              className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-bold text-lg transition"
            >
              {injecting ? 'Injecting...' : 'Inject Credits'}
            </button>
            
            {!isOnline && (
              <p className="text-sm text-yellow-500 text-center">
                ⚠️ Bot is offline. Start the session first.
              </p>
            )}
          </form>
        </div>

        {/* Activity Logs */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Terminal className="w-6 h-6 text-green-400" />
            <h2 className="text-2xl font-bold">Recent Activity</h2>
          </div>
          
          <div className="space-y-3 max-h-[600px] overflow-y-auto">
            {logs.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No recent activity</p>
            ) : (
              logs.map((log, idx) => (
                <div
                  key={`${log.timestamp}-${log.action}-${idx}`}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      {log.status === 'success' ? (
                        <CheckCircle className="w-5 h-5 text-green-400" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-400" />
                      )}
                      <div>
                        <p className="font-medium">{log.action}</p>
                        <p className="text-sm text-gray-400">
                          Player: {log.playerId} | Credits: {log.credits}
                        </p>
                        {log.error && (
                          <p className="text-sm text-red-400 mt-1">{log.error}</p>
                        )}
                      </div>
                    </div>
                    <span className="text-xs text-gray-500">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Platform Info */}
      <div className="max-w-7xl mx-auto mt-8 bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-xl font-bold mb-4">Platform Configuration</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-400">Platform ID:</span>
            <span className="ml-2 font-mono">{platformId}</span>
          </div>
          <div>
            <span className="text-gray-400">Agent URL:</span>
            <span className="ml-2 font-mono text-blue-400">{platform.adminUrl}</span>
          </div>
          <div>
            <span className="text-gray-400">Has Session Cookie:</span>
            <span className="ml-2">{platformStatus?.has_session_cookie ? '✅' : '❌'}</span>
          </div>
          <div>
            <span className="text-gray-400">Has CSRF Token:</span>
            <span className="ml-2">{platformStatus?.has_csrf_token ? '✅' : '❌'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

const StatusCard = ({ icon, label, value, color }) => {
  const colorClasses = {
    green: 'bg-green-500/20 text-green-400 border-green-500/30',
    red: 'bg-red-500/20 text-red-400 border-red-500/30',
    yellow: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    blue: 'bg-blue-500/20 text-blue-400 border-blue-500/30'
  };

  return (
    <div className={`border rounded-xl p-6 ${colorClasses[color]}`}>
      <div className="flex items-center gap-3 mb-2">
        {icon}
        <span className="text-sm font-medium text-gray-400">{label}</span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
};

export default MasterControl;

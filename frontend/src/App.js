import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Button } from './components/ui/button';
import { Badge } from './components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Calendar, User, Clock, MapPin, DollarSign, Eye, Trash2 } from 'lucide-react';
import './App.css';

const API_BASE_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [bookings, setBookings] = useState([]);
  const [activeBookings, setActiveBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    total: 0,
    active: 0,
    revenue: 0
  });

  useEffect(() => {
    fetchBookings();
    fetchActiveBookings();
    calculateStats();
  }, []);

  const fetchBookings = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/bookings`);
      setBookings(response.data);
    } catch (error) {
      console.error('Error fetching bookings:', error);
    }
  };

  const fetchActiveBookings = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/bookings/active`);
      setActiveBookings(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching active bookings:', error);
      setLoading(false);
    }
  };

  const calculateStats = async () => {
    try {
      const [allBookings, activeBookings] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/bookings`),
        axios.get(`${API_BASE_URL}/api/bookings/active`)
      ]);
      
      const currentMonth = new Date();
      currentMonth.setDate(1);
      currentMonth.setHours(0, 0, 0, 0);
      
      const monthlyRevenue = allBookings.data
        .filter(booking => {
          const bookingDate = new Date(booking.created_at);
          return bookingDate >= currentMonth && booking.status !== 'cancelled';
        })
        .reduce((sum, booking) => sum + booking.price, 0);

      setStats({
        total: allBookings.data.length,
        active: activeBookings.data.length,
        revenue: monthlyRevenue
      });
    } catch (error) {
      console.error('Error calculating stats:', error);
    }
  };

  const updateBookingStatus = async (bookingId, newStatus) => {
    try {
      await axios.put(`${API_BASE_URL}/api/bookings/${bookingId}/status?status=${newStatus}`);
      fetchBookings();
      fetchActiveBookings();
      calculateStats();
    } catch (error) {
      console.error('Error updating booking status:', error);
    }
  };

  const deleteBooking = async (bookingId) => {
    if (window.confirm('Вы уверены, что хотите удалить это бронирование?')) {
      try {
        await axios.delete(`${API_BASE_URL}/api/bookings/${bookingId}`);
        fetchBookings();
        fetchActiveBookings();
        calculateStats();
      } catch (error) {
        console.error('Error deleting booking:', error);
      }
    }
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      pending: { label: 'Ожидает', variant: 'secondary' },
      confirmed: { label: 'Подтверждено', variant: 'default' },
      completed: { label: 'Завершено', variant: 'outline' },
      cancelled: { label: 'Отменено', variant: 'destructive' }
    };
    
    const statusInfo = statusMap[status] || { label: status, variant: 'secondary' };
    return <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>;
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('ru-RU');
  };

  const BookingCard = ({ booking, showActions = true }) => (
    <Card className="mb-4 border-l-4 border-l-blue-500">
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="text-lg">
              {booking.first_name || 'Неизвестно'} 
              {booking.username && <span className="text-sm text-gray-500 ml-2">@{booking.username}</span>}
            </CardTitle>
            <CardDescription className="text-sm">
              ID: {booking.id.substring(0, 8)}...
            </CardDescription>
          </div>
          <div className="text-right">
            {getStatusBadge(booking.status)}
            <div className="text-lg font-bold text-green-600 mt-1">
              {booking.price}₽
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex items-center text-sm text-gray-600">
              <Eye className="w-4 h-4 mr-2" />
              <span>{booking.masks_count} маски на {booking.days_count} дн.</span>
            </div>
            <div className="flex items-center text-sm text-gray-600">
              <Calendar className="w-4 h-4 mr-2" />
              <span>{formatDate(booking.start_date)} - {formatDate(booking.end_date)}</span>
            </div>
            <div className="flex items-center text-sm text-gray-600">
              <Clock className="w-4 h-4 mr-2" />
              <span>Создано: {formatDate(booking.created_at)}</span>
            </div>
          </div>
          <div>
            <div className="flex items-start text-sm text-gray-600">
              <MapPin className="w-4 h-4 mr-2 mt-0.5 flex-shrink-0" />
              <span>{booking.delivery_address}</span>
            </div>
          </div>
        </div>
        
        {showActions && (
          <div className="flex gap-2 mt-4 pt-4 border-t">
            {booking.status === 'pending' && (
              <Button 
                size="sm" 
                onClick={() => updateBookingStatus(booking.id, 'confirmed')}
                className="bg-green-600 hover:bg-green-700"
              >
                Подтвердить
              </Button>
            )}
            {booking.status === 'confirmed' && (
              <Button 
                size="sm"
                variant="outline"
                onClick={() => updateBookingStatus(booking.id, 'completed')}
              >
                Завершить
              </Button>
            )}
            <Button 
              size="sm"
              variant="outline"
              onClick={() => updateBookingStatus(booking.id, 'cancelled')}
            >
              Отменить
            </Button>
            <Button 
              size="sm"
              variant="destructive"
              onClick={() => deleteBooking(booking.id)}
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-lg border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                🥽 Meta Quest 3 - Админ панель
              </h1>
              <p className="text-gray-600 mt-1">Управление арендой VR-масок</p>
            </div>
            <div className="text-right">
              <div className="text-sm text-gray-500">Telegram Bot: @vr_rental_bot</div>
              <div className="text-sm text-gray-500">Admin: @andrisxxx</div>
            </div>
          </div>
        </div>
      </header>

      {/* Stats Cards */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="bg-white shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Всего бронирований</p>
                  <p className="text-3xl font-bold text-gray-900">{stats.total}</p>
                </div>
                <User className="w-8 h-8 text-blue-600" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-white shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Активных бронирований</p>
                  <p className="text-3xl font-bold text-green-600">{stats.active}</p>
                </div>
                <Calendar className="w-8 h-8 text-green-600" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-white shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Доход за месяц</p>
                  <p className="text-3xl font-bold text-green-600">{stats.revenue}₽</p>
                </div>
                <DollarSign className="w-8 h-8 text-green-600" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="active" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-6">
            <TabsTrigger value="active" className="text-base">
              Активные бронирования ({activeBookings.length})
            </TabsTrigger>
            <TabsTrigger value="all" className="text-base">
              Все бронирования ({bookings.length})
            </TabsTrigger>
          </TabsList>
          
          <TabsContent value="active" className="space-y-4">
            {activeBookings.length === 0 ? (
              <Card className="bg-white">
                <CardContent className="p-12 text-center">
                  <Calendar className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    Нет активных бронирований
                  </h3>
                  <p className="text-gray-600">
                    Активные бронирования появятся здесь
                  </p>
                </CardContent>
              </Card>
            ) : (
              activeBookings.map(booking => (
                <BookingCard key={booking.id} booking={booking} />
              ))
            )}
          </TabsContent>
          
          <TabsContent value="all" className="space-y-4">
            {bookings.length === 0 ? (
              <Card className="bg-white">
                <CardContent className="p-12 text-center">
                  <User className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    Нет бронирований
                  </h3>
                  <p className="text-gray-600">
                    Бронирования появятся здесь после первых заказов через бота
                  </p>
                </CardContent>
              </Card>
            ) : (
              bookings.map(booking => (
                <BookingCard key={booking.id} booking={booking} />
              ))
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="text-center text-gray-600">
            <p>© 2024 Meta Quest 3 Rental Bot - Админ панель</p>
            <p className="text-sm mt-1">Powered by FastAPI + React + MongoDB</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
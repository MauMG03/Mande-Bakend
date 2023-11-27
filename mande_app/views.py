from .models import Worker_Job, Service, Job
from users.models import CustomUser, Worker, Customer
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.extra.rate_limiter import RateLimiter
from rest_framework.views import APIView, Response
from .serializers import JobSerializer

import json

class JobsAPI(APIView):
    def get(self, request):
        serializer = JobSerializer(Job.objects.all(), many=True)
        data = serializer.data

        return Response({"status":"success","data":data},status=200)

class Worker_JobAPI(APIView):
    geolocator = Nominatim(user_agent="mandeAPI")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

    def get(self,request):
        data = []

        try:
            id_user = request.GET.get('id_user', None)
        except:
            return HttpResponse("No id provided",status=401)
        
        coor1 = CustomUser.objects.get(id=id_user).coordinate

        for w in Worker_Job.objects.all():
            distance = None
            
            if w.worker.user.coordinate != None and coor1 != None:
                distance = geodesic((coor1.latitude,coor1.longitude),
                                     (w.worker.user.coordinate.latitude,w.worker.user.coordinate.latitude)).km

            aux = {
                "id_worker":w.worker.id,
                "first_name":w.worker.user.first_name,
                "last_name":w.worker.user.last_name,
                "email":w.worker.user.email,
                "phone":w.worker.user.phone,
                "worker_available":w.worker.is_available,
                "job":w.job.name,
                "price":w.price,
                "description":w.description,
                "distance":distance,
                "rating":w.worker.rating,
                "photo":w.worker.user.photo
            }

            data.append(aux)
        
        return Response({"status":"success","data":data})
    
    def post(self,request):
        with transaction.atomic():
            try:
                id_user = self.request.data['id_user']
            except:
                return HttpResponse("No id provided",status=401)

            user = CustomUser.objects.get(id=id_user)
            if not(len(Worker.objects.filter(user=user)) == 1):
                return HttpResponse("User is not a worker",status=401)
            
            if len(Worker_Job.objects.filter(worker=Worker.objects.get(user=user),
                                    job=Job.objects.get(id=self.request.data['id_job']))) == 1:
                return HttpResponse("Job is already added",status=401)
            
            Worker_Job.objects.create(worker=Worker.objects.get(user=user),
                                    job=Job.objects.get(id=self.request.data['id_job']),
                                    price=self.request.data['price'],
                                    description=self.request.data['description'])
            
            return HttpResponse(f"Job added to worker user with id {id_user}",status=200)

    def delete(self,request):
        with transaction.atomic():
            try:
                id_user = self.request.data['id_user']
            except:
                return HttpResponse("No id of user provided",status=401)
            
            try:
                id_job = self.request.data['id_job']
            except:
                return HttpResponse("No id of job provided",status=401)

            user = CustomUser.objects.get(id=id_user)
            if not(len(Worker.objects.filter(user=user)) == 1):
                return HttpResponse("User is not a worker",status=401)
            
            if not(len(Worker_Job.objects.filter(worker=Worker.objects.get(user=user),
                                    job=Job.objects.get(id=id_job))) == 1):
                return HttpResponse("Worker is not related to the job",status=401)
            
            Worker_Job.objects.get(worker=Worker.objects.get(user=user),
                                    job=Job.objects.get(id=id_job)).delete()
            
            return HttpResponse(f"Job deleted from worker user with id {id_user}",status=200)

class ServiceAPI(APIView):
    def get(self,request):
        data = []

        if(request.data['role'] == 'customer'):
            services = Service.objects.filter(customer=Customer.objects.get(user=request.data['id_user']))
        elif(request.data['role'] == 'worker'):
            services = Service.objects.filter(worker_job=Worker_Job.objects.get(worker=Worker.objects.get(user=request.data['id_user'])))
                
        for s in services:
            aux = {
                "id":s.id,
                "customer_name":s.customer.user.first_name,
                "customer_last_name":s.customer.user.last_name,
                "customer_email":s.customer.user.email,
                "customer_phone":s.customer.user.phone,
                "worker_name":s.worker_job.worker.user.first_name,
                "worker_last_name":s.worker_job.worker.user.last_name,
                "worker_email":s.worker_job.worker.user.email,
                "worker_phone":s.worker_job.worker.user.phone,
                "job":s.worker_job.job.name,
                "price":s.worker_job.price,
                "hours":s.hours,
                "cost":s.cost,
                "status":s.status,
                "date":s.date,
                "description":s.description
            }
            data.append(aux)
        
        return Response({"status":"success","data":data})
    
    def post(self,request):
        with transaction.atomic():
            id_customer = self.request.data['id_customer']
            worker_job = Worker_Job.objects.get(id=self.request.data['id_worker_job'])
            worker = worker_job.worker

            if(not worker.is_available):
                return HttpResponse("Worker is not available",status=401)

            worker.is_available = False
            worker.save()
            
            Service.objects.create(
                customer=Customer.objects.get(user=CustomUser.objects.get(id=id_customer)),
                worker_job=worker_job,
                date=timezone.now(),
                status=True,
                hours=self.request.data['hours'],
                cost=float(worker_job.price)*float(self.request.data['hours']),
                rating=None,
                description=self.request.data['description'])
            
            return HttpResponse(f"Service requested by customer {id_customer} created, job:{worker_job.job.name}",status=200)
    
    def patch(self,request):
        with transaction.atomic():
            service = Service.objects.get(id=self.request.data['id_service'])

            if(not service.status):
                return HttpResponse("Service already ended",status=401)

            service.status = False
            service.rating = self.request.data['rating']
            service.save()
            
            worker = service.worker_job.worker

            # Counting the number of services where the worker has been rated
            num_services = 0
            for s in Service.objects.all():
                if(s.worker_job.worker == worker and s.rating != None):
                    num_services += 1

            # Calculating the new rating
            worker.rating = (worker.rating*(num_services-1) + float(self.request.data['rating']))/(num_services)
            worker.is_available = True
            worker.save()
            
            return HttpResponse(f"Service with id {self.request.data['id_service']} updated",status=200)

    def delete(self,request):
        Service.objects.get(id=self.request.data['id_service']).delete()
        
        return HttpResponse(f"Service {self.request.data['id_service']} deleted",status=200)
